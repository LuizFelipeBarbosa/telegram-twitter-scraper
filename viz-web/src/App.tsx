import { Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { ComingSoonPanel } from "./components/ComingSoonPanel";
import { LandscapeView } from "./views/LandscapeView";
import { NodeDetailView } from "./views/NodeDetailView";

export default function App() {
  return (
    <AppShell>
      <Routes>
        <Route path="/" element={<LandscapeView />} />
        <Route path="/node/:kind/:slug" element={<NodeDetailView />} />
        <Route
          path="/trends"
          element={
            <ComingSoonPanel
              title="Trends view is next."
              description="Emerging, flash, and fading trend cards land in the next phase."
            />
          }
        />
        <Route
          path="/propagation"
          element={
            <ComingSoonPanel
              title="Propagation view is next."
              description="Cross-channel timing and framing analysis is intentionally deferred in phase 1."
            />
          }
        />
        <Route
          path="/evolution"
          element={
            <ComingSoonPanel
              title="Evolution view is next."
              description="The animated graph timeline needs the later API endpoints and ships after the detail views are stable."
            />
          }
        />
      </Routes>
    </AppShell>
  );
}
