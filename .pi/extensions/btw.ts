import type { ExtensionAPI, ExtensionCommandContext } from "@mariozechner/pi-coding-agent";
import { BorderedLoader, DynamicBorder, getMarkdownTheme } from "@mariozechner/pi-coding-agent";
import { Container, Markdown, Text, matchesKey } from "@mariozechner/pi-tui";
import { getPreferredProjectModelArg, PREFERRED_PROJECT_MODEL } from "./lib/preferred-model";
import { askProjectSideQuestion } from "./lib/project-side-question";

async function showAnswerUi(prompt: string, answer: string, ctx: ExtensionCommandContext) {
	await ctx.ui.custom((_tui, theme, _kb, done) => {
		const container = new Container();
		const border = new DynamicBorder((s: string) => theme.fg("accent", s));
		const mdTheme = getMarkdownTheme();

		container.addChild(border);
		container.addChild(new Text(theme.fg("accent", theme.bold("BTW")), 1, 0));
		container.addChild(new Text(theme.fg("muted", `${prompt} · ${PREFERRED_PROJECT_MODEL}`), 1, 0));
		container.addChild(new Markdown(answer, 1, 1, mdTheme));
		container.addChild(new Text(theme.fg("dim", "Press Enter or Esc to close"), 1, 0));
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

export default function (pi: ExtensionAPI) {
	pi.registerCommand("btw", {
		description: `Ask a one-off side question with project context using ${PREFERRED_PROJECT_MODEL}, without adding it to the session`,
		handler: async (args, ctx) => {
			const prompt = args.trim();

			if (!prompt) {
				if (ctx.hasUI) ctx.ui.notify("Usage: /btw <prompt>", "warning");
				else process.stderr.write("Usage: /btw <prompt>\n");
				return;
			}

			const thinkingArg = pi.getThinkingLevel();
			let modelArg: string;
			try {
				modelArg = getPreferredProjectModelArg(ctx);
			} catch (err) {
				const message = err instanceof Error ? err.message : String(err);
				if (ctx.hasUI) ctx.ui.notify(message, "error");
				else process.stderr.write(`${message}\n`);
				return;
			}

			if (!ctx.hasUI) {
				try {
					const answer = await askProjectSideQuestion(prompt, {
						cwd: ctx.cwd,
						modelArg,
						thinkingArg,
					});
					process.stdout.write(`${answer}\n`);
				} catch (err) {
					process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
				}
				return;
			}

			let errorMessage: string | undefined;

			const answer = await ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
				const loader = new BorderedLoader(tui, theme, `Asking project side question with ${PREFERRED_PROJECT_MODEL}...`);
				loader.onAbort = () => done(null);

				askProjectSideQuestion(prompt, {
					cwd: ctx.cwd,
					modelArg,
					thinkingArg,
					signal: loader.signal,
				})
					.then((result) => done(result))
					.catch((err) => {
						errorMessage = err instanceof Error ? err.message : String(err);
						done(null);
					});

				return loader;
			});

			if (answer === null) {
				ctx.ui.notify(errorMessage ?? "Cancelled", errorMessage ? "error" : "info");
				return;
			}

			await showAnswerUi(prompt, answer, ctx);
		},
	});
}
