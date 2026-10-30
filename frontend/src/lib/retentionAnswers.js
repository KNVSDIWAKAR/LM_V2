// Presentation only: never re-evaluate a loan or change a saved case verdict here.
// Older reports may contain pending badges based solely on retired confidence rules.
export function answerPresentation(answer, stips = []) {
  const hasStip = stips.some((stip) => stip.question_id === answer.question_id &&
    (stip.wage_number == null || stip.wage_number === answer.wage_number));
  const dateOnly = answer.display_type === "date" || ["Q5", "CALC_Q4"].includes(answer.question_id);
  let result;
  if (hasStip || answer.result === "fail") result = "fail";
  else if (answer.not_applicable) result = "pass";
  else if (dateOnly || answer.result === "neutral" || answer.answer == null) result = "neutral";
  else result = "pass";
  return { result, dateOnly, badge: result === "neutral" ? null : result };
}

export function answerSummary(answers = [], stips = []) {
  return answers.reduce((totals, answer) => {
    totals[answerPresentation(answer, stips).result] += 1;
    return totals;
  }, { pass: 0, fail: 0, neutral: 0 });
}