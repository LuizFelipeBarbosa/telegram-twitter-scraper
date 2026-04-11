const palette = [
  "#c65d2e",
  "#0d7c66",
  "#286fb4",
  "#9a3412",
  "#6d28d9",
  "#a16207",
  "#be185d",
  "#0369a1",
  "#4d7c0f",
  "#7c3aed",
];

export function buildChannelColorMap(channelIds: number[]): Map<number, string> {
  const sorted = [...channelIds].sort((left, right) => left - right);
  return new Map(sorted.map((channelId, index) => [channelId, palette[index % palette.length]]));
}
