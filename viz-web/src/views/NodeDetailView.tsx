import { useParams } from "react-router-dom";
import { ConnectedNodesRail } from "../components/ConnectedNodesRail";
import { EmptyState } from "../components/EmptyState";
import { LoadingState } from "../components/LoadingState";
import { NodeHeaderBand } from "../components/NodeHeaderBand";
import { NodeStoriesList } from "../components/NodeStoriesList";
import { ThemeHistory } from "../components/ThemeHistory";
import { Breadcrumbs } from "../layout/Breadcrumbs";
import { useAsyncResource } from "../hooks/useAsyncResource";
import { fetchNodeDetail, fetchThemeHistory } from "../lib/api";
import { KIND_LABEL, MetricCell, MetricsStrip } from "../ui";

export function NodeDetailView() {
  const { kind, slug } = useParams<{ kind: string; slug: string }>();

  const detailState = useAsyncResource(() => fetchNodeDetail(kind ?? "", slug ?? ""), [kind, slug]);
  const historyState = useAsyncResource(
    () => (kind === "theme" && slug ? fetchThemeHistory(slug) : Promise.resolve(null)),
    [kind, slug],
  );

  if (!kind || !slug) {
    return <EmptyState title="Node not found" message="Choose a node from the landscape to inspect it in detail." />;
  }

  if (detailState.loading || historyState.loading) {
    return <LoadingState />;
  }

  if (detailState.error || !detailState.data) {
    return <EmptyState title="Node detail unavailable" message="This node could not be loaded from the visualization API." />;
  }

  const detail = detailState.data;
  const history = historyState.data?.history ?? [];
  const latestDrift = history.length > 0 ? history[history.length - 1].centroid_drift : null;
  const themePhase = detail.kind === "theme" ? "steady" : null;

  const connectedCount =
    detail.events.length +
    detail.people.length +
    detail.nations.length +
    detail.orgs.length +
    detail.places.length +
    detail.themes.length;

  return (
    <section>
      <Breadcrumbs kind={detail.kind} displayName={detail.display_name} />
      <NodeHeaderBand detail={detail} phase={themePhase} />

      <div className="mx-5">
        <MetricsStrip>
          <MetricCell label="Kind" value={KIND_LABEL[detail.kind]} caption={detail.slug} />
          <MetricCell label="Stories" value={detail.article_count} caption="across sources" />
          <MetricCell label="Connected" value={connectedCount} caption="related nodes" />
          {detail.kind === "theme" ? (
            <MetricCell label="Phase" value={themePhase ?? "—"} caption="current lifecycle" />
          ) : null}
          {detail.kind === "theme" ? (
            <MetricCell
              label="Drift"
              value={latestDrift != null ? latestDrift.toFixed(3) : "—"}
              caption="centroid"
            />
          ) : null}
        </MetricsStrip>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)] border-b border-ink">
        <div className="px-5 py-5 border-r border-ink/20 flex flex-col gap-6">
          {detail.kind === "theme" ? <ThemeHistory history={history} /> : null}
          <NodeStoriesList stories={detail.stories} />
        </div>
        <div className="px-5 py-5">
          <ConnectedNodesRail detail={detail} />
        </div>
      </div>
    </section>
  );
}
