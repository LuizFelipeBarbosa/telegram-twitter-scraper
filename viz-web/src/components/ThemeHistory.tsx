import { Bar, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ThemeHistoryPoint } from "../lib/types";
import { Eyebrow } from "../ui";

interface ThemeHistoryProps {
  history: ThemeHistoryPoint[];
}

export function ThemeHistory({ history }: ThemeHistoryProps) {
  const data = history.map((point) => ({
    ...point,
    dateLabel: new Date(point.date).toLocaleDateString(undefined, { month: "short", day: "numeric" }),
  }));

  return (
    <section>
      <Eyebrow>Volume and drift</Eyebrow>
      <h2 className="text-[1.2rem] mt-0.5 mb-3">Theme evolution over time</h2>
      {data.length === 0 ? (
        <p className="text-[0.78rem] text-muted border-t border-ink/15 pt-3">No history yet for this theme.</p>
      ) : (
        <div className="border-t border-ink/15 pt-2">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={data} margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
              <XAxis
                dataKey="dateLabel"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <YAxis
                yAxisId="left"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tickLine={false}
                axisLine={{ stroke: "rgba(26,23,21,0.16)" }}
                tick={{ fill: "#8B5E3C", fontSize: 10, fontFamily: "JetBrains Mono, monospace" }}
              />
              <Tooltip
                contentStyle={{ background: "#FDF9EC", border: "1px solid #1A1715", borderRadius: 2, fontSize: 12 }}
                labelStyle={{ color: "#1A1715" }}
              />
              <Bar yAxisId="left" dataKey="article_count" fill="#0D7C66" radius={[2, 2, 0, 0]} />
              <Line yAxisId="right" dataKey="centroid_drift" stroke="#C94F2B" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
