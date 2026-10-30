import { Route, Switch } from "wouter";
import AppLayout from "./components/layout/AppLayout";
import AgentConsole from "./pages/AgentConsole";
import AgentRuns from "./pages/AgentRuns";
import CommandCenter from "./pages/CommandCenter";
import DecisionInbox from "./pages/DecisionInbox";
import KnowledgeBase from "./pages/KnowledgeBase";
import LossMitigationDashboard from "./pages/LossMitigationDashboard";
import LossMitigationEndToEnd from "./pages/LossMitigationEndToEnd";
import NotFound from "./pages/NotFound";
import Playbooks from "./pages/Playbooks";
import Systems from "./pages/Systems";
import WorkflowRuns from "./pages/WorkflowRuns";
import {
  FinalModClosing,
  IntakeDocReview,
  RetentionEligibility,
  TrialMonitoring,
  TrialUnderwriting,
} from "./pages/JourneyPages";

export default function App() {
  return (
    <AppLayout>
      <Switch>
        <Route path="/" component={CommandCenter} />
        <Route path="/agent-console" component={AgentConsole} />
        <Route path="/loss-mitigation" component={LossMitigationEndToEnd} />
        <Route path="/loss-mitigation-dashboard" component={LossMitigationDashboard} />
        <Route path="/loss-mit-intake" component={IntakeDocReview} />
        <Route path="/loss-mit" component={RetentionEligibility} />
        <Route path="/loss-mit-trial-uw" component={TrialUnderwriting} />
        <Route path="/loss-mit-trial" component={TrialMonitoring} />
        <Route path="/loss-mit-closing" component={FinalModClosing} />
        <Route path="/knowledge-base" component={KnowledgeBase} />
        <Route path="/playbooks" component={Playbooks} />
        <Route path="/systems" component={Systems} />
        <Route path="/decision-inbox/:id" component={DecisionInbox} />
        <Route path="/decision-inbox" component={DecisionInbox} />
        <Route path="/agent-runs" component={AgentRuns} />
        <Route path="/workflow-runs" component={WorkflowRuns} />
        <Route>
          <NotFound title="Page Not Found" />
        </Route>
      </Switch>
    </AppLayout>
  );
}
