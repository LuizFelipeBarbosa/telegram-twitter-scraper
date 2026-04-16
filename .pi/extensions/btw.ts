import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionCommandContext } from "@mariozechner/pi-coding-agent";
import { BorderedLoader, DynamicBorder, getMarkdownTheme } from "@mariozechner/pi-coding-agent";
import { Container, Markdown, Text, matchesKey } from "@mariozechner/pi-tui";

type JsonMessage = {
	role?: string;
	content?: Array<{ type?: string; text?: string }>;
	errorMessage?: string;
};

type JsonEvent = {
	type?: string;
	message?: JsonMessage;
};

function getPiInvocation(): { command: string; argsPrefix: string[] } {
	const currentScript = process.argv[1];
	const isBunVirtualScript = currentScript?.startsWith("/$bunfs/root/");

	if (currentScript && !isBunVirtualScript && fs.existsSync(currentScript)) {
		return { command: process.execPath, argsPrefix: [currentScript] };
	}

	const execName = path.basename(process.execPath).toLowerCase();
	const isGenericRuntime = /^(node|bun)(\.exe)?$/.test(execName);
	if (!isGenericRuntime) {
		return { command: process.execPath, argsPrefix: [] };
	}

	return { command: "pi", argsPrefix: [] };
}

function extractAssistantText(message: JsonMessage | undefined): string {
	if (!message?.content || !Array.isArray(message.content)) return "";

	return message.content
		.filter(
			(part): part is { type: "text"; text: string } =>
				part?.type === "text" && typeof part.text === "string",
		)
		.map((part) => part.text)
		.join("\n")
		.trim();
}

async function askProjectSideQuestion(
	ctx: ExtensionCommandContext,
	prompt: string,
	modelArg: string | undefined,
	thinkingArg: string,
	signal?: AbortSignal,
): Promise<string> {
	const { command, argsPrefix } = getPiInvocation();

	const args = [
		...argsPrefix,
		"--mode",
		"json",
		"-p",
		"--no-session",
		"--no-extensions",
		"--tools",
		"read,grep,find,ls",
		"--append-system-prompt",
		[
			"This is a quick side question about the current project.",
			"Use the project context and read-only tools if helpful.",
			"Do not modify files.",
			"Answer directly and concisely.",
		].join(" "),
		"--thinking",
		thinkingArg,
	];

	if (modelArg) {
		args.push("--model", modelArg);
	}

	args.push(["Quick side question about the current project:", "", prompt].join("\n"));

	return await new Promise<string>((resolve, reject) => {
		let stdoutBuffer = "";
		let stderr = "";
		let lastAssistantText = "";
		let lastErrorMessage = "";
		let aborted = false;

		const child = spawn(command, args, {
			cwd: ctx.cwd,
			stdio: ["ignore", "pipe", "pipe"],
		});

		const processLine = (line: string) => {
			if (!line.trim()) return;

			let event: JsonEvent;
			try {
				event = JSON.parse(line) as JsonEvent;
			} catch {
				return;
			}

			if (event.type === "message_end" && event.message?.role === "assistant") {
				const text = extractAssistantText(event.message);
				if (text) lastAssistantText = text;
				if (event.message.errorMessage) lastErrorMessage = event.message.errorMessage;
			}
		};

		child.stdout.on("data", (chunk: Buffer | string) => {
			stdoutBuffer += chunk.toString();
			const lines = stdoutBuffer.split("\n");
			stdoutBuffer = lines.pop() ?? "";
			for (const line of lines) processLine(line);
		});

		child.stderr.on("data", (chunk: Buffer | string) => {
			stderr += chunk.toString();
		});

		child.on("error", (err) => reject(err));

		child.on("close", (code) => {
			if (stdoutBuffer.trim()) processLine(stdoutBuffer);

			if (aborted) {
				reject(new Error("Cancelled"));
				return;
			}

			if (lastErrorMessage) {
				reject(new Error(lastErrorMessage));
				return;
			}

			if ((code ?? 0) !== 0 && !lastAssistantText) {
				reject(new Error(stderr.trim() || `btw subprocess exited with code ${code}`));
				return;
			}

			resolve(lastAssistantText || "(No text response)");
		});

		if (signal) {
			const abort = () => {
				aborted = true;
				child.kill("SIGTERM");
				setTimeout(() => {
					if (!child.killed) child.kill("SIGKILL");
				}, 5000);
			};

			if (signal.aborted) abort();
			else signal.addEventListener("abort", abort, { once: true });
		}
	});
}

async function showAnswerUi(prompt: string, answer: string, ctx: ExtensionCommandContext) {
	await ctx.ui.custom((_tui, theme, _kb, done) => {
		const container = new Container();
		const border = new DynamicBorder((s: string) => theme.fg("accent", s));
		const mdTheme = getMarkdownTheme();

		container.addChild(border);
		container.addChild(new Text(theme.fg("accent", theme.bold("BTW")), 1, 0));
		container.addChild(new Text(theme.fg("muted", prompt), 1, 0));
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
		description: "Ask a one-off side question with project context, without adding it to the session",
		handler: async (args, ctx) => {
			const prompt = args.trim();

			if (!prompt) {
				if (ctx.hasUI) ctx.ui.notify("Usage: /btw <prompt>", "warning");
				else process.stderr.write("Usage: /btw <prompt>\n");
				return;
			}

			const modelArg = ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : undefined;
			const thinkingArg = pi.getThinkingLevel();

			if (!ctx.hasUI) {
				try {
					const answer = await askProjectSideQuestion(ctx, prompt, modelArg, thinkingArg);
					process.stdout.write(`${answer}\n`);
				} catch (err) {
					process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
				}
				return;
			}

			let errorMessage: string | undefined;

			const answer = await ctx.ui.custom<string | null>((tui, theme, _kb, done) => {
				const loader = new BorderedLoader(tui, theme, "Asking project side question...");
				loader.onAbort = () => done(null);

				askProjectSideQuestion(ctx, prompt, modelArg, thinkingArg, loader.signal)
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
