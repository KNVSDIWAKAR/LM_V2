import ProcessPage from "./ProcessPage";
import RetentionPage from "./RetentionEligibility";

export const IntakeDocReview = () => <ProcessPage stageNo={1} />;
export const RetentionEligibility = () => <RetentionPage />;
export const TrialUnderwriting = () => <ProcessPage stageNo={3} />;
export const TrialMonitoring = () => <ProcessPage stageNo={4} />;
export const FinalModClosing = () => <ProcessPage stageNo={5} />;
