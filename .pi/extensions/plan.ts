import { BorderedLoader, DynamicBorder, getMarkdownTheme } from "@mariozechner/pi-coding-agent";
import type { ExtensionAPI, ExtensionCommandContext } from "@mariozechner/pi-coding-agent";
import { Container, Markdown, Text, matchesKey } from "@mariozechner/pi-tui";
import { getPreferredProjectModelArg, PREFERRED_PROJECT_MODEL } from "./lib/preferred-model";
import { askProjectSideQuestion } from "./lib/project-side-question";

const SYSTEM_PROMPT = `You turn rough feature ideas into clear, repository-aware, implementation-ready prompts for a coding agent.

Your job is to preserve the user's intent while making the task easier to understand and easier to execute inside the current codebase.

What good output looks like:
- Clear goal stated in plain language
- Scope is concrete and not over-engineered
- Important constraints or assumptions are explicit
- A small MVP path is preferred when the request is broad
- Success criteria are easy to verify
- The wording is accessible to someone new to the codebase
- When repository context is available, the prompt mentions the most relevant files, commands, tests, or docs

When useful, structure the prompt with sections like:
## Goal
## Scope
## Constraints / Assumptions
## Implementation outline
## Acceptance criteria
## Open questions

Rules:
- Output only the final improved prompt in markdown.
- Do not say that you are rewriting or improving the prompt.
- Do not wrap the entire answer in code fences.
- Keep it concise, but specific enough to act on.
- Use repository context when supported by evidence.
- Do not invent files, architecture, or subsystems that are not supported by the context.
- If a file or approach is only a likely candidate, label it as likely.
- Make reasonable assumptions instead of inventing unnecessary complexity.
- Add an "Open questions" section only when missing information is genuinely important.`;

type PlanGenerationResult = {
	improvedPrompt: string;
	repositoryContext: string;
};

async function getDraftPrompt(args: string, ctx: ExtensionCommandContext): Promise<string | null> {
	const fromArgs = args.trim();
	if (fromArgs) return fromArgs;

	if (!ctx.hasUI) {
		process.stderr.write("Usage: /plan <prompt>\n");
		return null;
	}

	const draft = await ctx.ui.editor("Draft prompt to improve", "");
	if (draft === undefined) return null;

	const trimmed = draft.trim();
	if (!trimmed) {
		ctx.ui.notify("No prompt provided", "warning");
		return null;
	}

	return trimmed;
}

async function showRepositoryReconUi(repositoryContext: string, ctx: ExtensionCommandContext) {
	if (!ctx.hasUI || !repositoryContext.trim()) {
		return;
	}

	await ctx.ui.custom((_tui, theme, _kb, done) => {
		const container = new Container();
		const border = new DynamicBorder((s: string) => theme.fg("accent", s));
		const mdTheme = getMarkdownTheme();

		container.addChild(border);
		container.addChild(new Text(theme.fg("accent", theme.bold("Plan repo reconnaissance")), 1, 0));
		container.addChild(new Text(theme.fg("muted", `Discovered files and repo notes from ${PREFERRED_PROJECT_MODEL}`), 1, 0));
		container.addChild(new Markdown(repositoryContext, 1, 1, mdTheme));
		container.addChild(new Text(theme.fg("dim", "Press Enter or Esc to load the improved prompt into the editor"), 1, 0));
		container.addChild(border);

		return {
			render: (width: number) => container.render(width),
			invalidate: () => container.invalidate(),
			handleInput: (data: string) => {
				if (matchesKey(data, "enter") || matchesKey(data, "escape")) {
					done(undefined);
				}
			},
		};
	});
}

async function inspectRepositoryForPrompt(
	pi: ExtensionAPI,
	ctx: ExtensionCommandContext,
	draft: string,
	signal?: AbortSignal,
): Promise<string> {
	const prompt = [
		"Inspect the current repository and summarize only the information that would help turn the request below into an implementation-ready coding prompt.",
		"Focus on concrete evidence from the repo.",
		"",
		"Return concise markdown with these sections when possible:",
		"## Likely relevant files",
		"- Include explicit file paths and a short reason each matters",
		"## Repo summary",
		"## Constraints / notes",
		"## Open questions",
		"",
		"Rules:",
		"- Mention explicit file paths when you have evidence.",
		"- Prefer existing code, docs, tests, and commands over speculation.",
		"- If something is only a likely candidate, say 'likely'.",
		"- Keep the answer concise.",
		"",
		"<request>",
		draft,
		"</request>",
	].join("\n");

	try {
		const result = await askProjectSideQuestion(prompt, {
			cwd: ctx.cwd,
			modelArg: getPreferredProjectModelArg(ctx),
			thinkingArg: "off",
			signal,
			systemPrompt: [
				"This is repository reconnaissance for a planning command.",
				"Explore the current project with read-only tools if useful.",
				"Do not modify files.",
				"Answer in concise markdown grounded in repository evidence.",
			].join(" "),
		});
		return result === "(No text response)" ? "" : result.trim();
	} catch {
		return "";
	}
}

async function generatePlanResult(
	pi: ExtensionAPI,
	ctx: ExtensionCommandContext,
	draft: string,
	signal?: AbortSignal,
): Promise<PlanGenerationResult> {
	const modelArg = getPreferredProjectModelArg(ctx);
	const repositoryContext = await inspectRepositoryForPrompt(pi, ctx, draft, signal);
	const promptParts = [
		"Rewrite the following rough implementation idea into a clearer, more accessible, implementation-ready prompt.",
		"Prefer a practical MVP, concrete scope, and explicit success criteria.",
		"Use the repository context to ground the prompt in the actual codebase when possible.",
		"Mention likely files, tests, commands, or docs when the repo context supports them.",
		"If something is uncertain, label it as likely rather than stating it as fact.",
	];

	if (repositoryContext) {
		promptParts.push("", "<repository-context>", repositoryContext, "</repository-context>");
	}

	promptParts.push("", "<draft-prompt>", draft, "</draft-prompt>");

	const improvedPrompt = await askProjectSideQuestion(promptParts.join("\n"), {
		cwd: ctx.cwd,
		modelArg,
		thinkingArg: "off",
		tools: null,
		signal,
		systemPrompt: [
			SYSTEM_PROMPT,
			"This is the final /plan prompt-generation step.",
			"Use only the provided repository context and the user draft.",
			"Do not inspect the repository further unless the prompt explicitly includes that context.",
			"Do not modify files.",
			"Output only the final improved prompt in markdown.",
		].join(" "),
	});

	if (!improvedPrompt || improvedPrompt === "(No text response)") {
		throw new Error("Model returned an empty prompt");
	}

	return { improvedPrompt: improvedPrompt.trim(), repositoryContext };
}

export default function planExtension(pi: ExtensionAPI) {
	pi.registerCommand("plan", {
		description: `Turn a rough idea into a repo-aware implementation-ready prompt using ${PREFERRED_PROJECT_MODEL}`,
		handler: async (args, ctx) => {
			const draft = await getDraftPrompt(args, ctx);
			if (!draft) return;

			if (!ctx.hasUI) {
				try {
					const result = await generatePlanResult(pi, ctx, draft);
					process.stdout.write(`${result.improvedPrompt}\n`);
				} catch (err) {
					process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
				}
				return;
			}

			let errorMessage: string | undefined;
			const result = await ctx.ui.custom<PlanGenerationResult | null>((tui, theme, _kb, done) => {
				const loader = new BorderedLoader(tui, theme, `Exploring repo and improving prompt with ${PREFERRED_PROJECT_MODEL}...`);
				loader.onAbort = () => done(null);

				generatePlanResult(pi, ctx, draft, loader.signal)
					.then((planResult) => done(planResult))
					.catch((err) => {
						errorMessage = err instanceof Error ? err.message : String(err);
						done(null);
					});

				return loader;
			});

			if (result === null) {
				ctx.ui.notify(errorMessage ?? "Cancelled", errorMessage ? "error" : "info");
				return;
			}

			if (result.repositoryContext) {
				await showRepositoryReconUi(result.repositoryContext, ctx);
			}

			ctx.ui.setEditorText(result.improvedPrompt);
			ctx.ui.notify("Improved prompt loaded into the editor. Review and submit when ready.", "info");
		},
	});
}
