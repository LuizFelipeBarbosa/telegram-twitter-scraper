import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

type JsonMessage = {
	role?: string;
	content?: Array<{ type?: string; text?: string }>;
	errorMessage?: string;
};

type JsonEvent = {
	type?: string;
	message?: JsonMessage;
};

export type AskProjectSideQuestionOptions = {
	cwd: string;
	modelArg?: string;
	thinkingArg?: string;
	tools?: string | null;
	systemPrompt?: string;
	signal?: AbortSignal;
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

export async function askProjectSideQuestion(
	prompt: string,
	options: AskProjectSideQuestionOptions,
): Promise<string> {
	const {
		cwd,
		modelArg,
		thinkingArg = "off",
		tools = "read,grep,find,ls",
		systemPrompt = [
			"This is a quick side question about the current project.",
			"Use the project context and read-only tools if helpful.",
			"Do not modify files.",
			"Answer directly and concisely.",
		].join(" "),
		signal,
	} = options;
	const { command, argsPrefix } = getPiInvocation();

	const args = [
		...argsPrefix,
		"--mode",
		"json",
		"-p",
		"--no-session",
		"--no-extensions",
	];

	if (tools !== null) {
		args.push("--tools", tools);
	}

	args.push("--append-system-prompt", systemPrompt, "--thinking", thinkingArg);

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
			cwd,
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
				reject(new Error(stderr.trim() || `pi subprocess exited with code ${code}`));
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
