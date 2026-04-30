import type { ExtensionCommandContext } from "@mariozechner/pi-coding-agent";

export const PREFERRED_PROJECT_MODEL_PROVIDER = "openai-codex";
export const PREFERRED_PROJECT_MODEL_ID = "gpt-5.4";
export const PREFERRED_PROJECT_MODEL = `${PREFERRED_PROJECT_MODEL_PROVIDER}/${PREFERRED_PROJECT_MODEL_ID}`;

export function getPreferredProjectModel(ctx: Pick<ExtensionCommandContext, "modelRegistry">) {
	const model = ctx.modelRegistry.find(PREFERRED_PROJECT_MODEL_PROVIDER, PREFERRED_PROJECT_MODEL_ID);
	if (!model) {
		throw new Error(`Preferred model ${PREFERRED_PROJECT_MODEL} not found`);
	}
	return model;
}

export function getPreferredProjectModelArg(ctx: Pick<ExtensionCommandContext, "modelRegistry">): string {
	const model = getPreferredProjectModel(ctx);
	return `${model.provider}/${model.id}`;
}
