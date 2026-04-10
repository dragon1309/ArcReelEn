import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { PendingQuestion } from "@/types";
import { PendingQuestionWizard } from "./PendingQuestionWizard";

function makePendingQuestion(overrides: Partial<PendingQuestion> = {}): PendingQuestion {
  return {
    question_id: "q-1",
    questions: [
      {
        header: "Output",
        question: "What output format should I use?",
        multiSelect: false,
        options: [
          { label: "Summary", description: "Concise response" },
          { label: "Detailed", description: "Complete explanation" },
        ],
      },
      {
        header: "Sections",
        question: "Which sections should be included?",
        multiSelect: true,
        options: [
          { label: "Introduction", description: "Opening context" },
          { label: "Conclusion", description: "Wrap-up summary" },
        ],
      },
    ],
    ...overrides,
  };
}

describe("PendingQuestionWizard", () => {
  it("renders only the current question and blocks next until answered", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByText("Question 1/2")).toBeInTheDocument();
    expect(screen.getByText("What output format should I use?")).toBeInTheDocument();
    expect(screen.queryByText("Which sections should be included?")).not.toBeInTheDocument();

    const nextButton = screen.getByRole("button", { name: "Next" });
    expect(nextButton).toBeDisabled();

    fireEvent.click(screen.getByLabelText("Summary"));
    expect(nextButton).toBeEnabled();

    fireEvent.click(nextButton);
    expect(screen.getByText("Question 2/2")).toBeInTheDocument();
    expect(screen.getByText("Which sections should be included?")).toBeInTheDocument();
    expect(screen.queryByText("What output format should I use?")).not.toBeInTheDocument();
  });

  it("keeps answers when navigating backward", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("Detailed"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous" }));

    expect(screen.getByText("What output format should I use?")).toBeInTheDocument();
    expect(screen.getByLabelText("Detailed")).toBeChecked();
  });

  it("validates custom other answers and joins multi-select payloads", () => {
    const onSubmitAnswers = vi.fn();

    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({
          questions: [
            {
              header: "Sections",
              question: "Which sections should be included?",
              multiSelect: true,
              options: [
                { label: "Introduction", description: "Opening context" },
                { label: "Conclusion", description: "Wrap-up summary" },
              ],
            },
          ],
        })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={onSubmitAnswers}
      />,
    );

    fireEvent.click(screen.getByLabelText("Introduction"));
    fireEvent.click(screen.getByLabelText("Other"));

    const submitButton = screen.getByRole("button", { name: "Finish and Submit" });
    expect(submitButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText("Enter another response"), {
      target: { value: "Appendix" },
    });
    expect(submitButton).toBeEnabled();

    fireEvent.click(submitButton);

    expect(onSubmitAnswers).toHaveBeenCalledWith("q-1", {
      "Which sections should be included?": "Introduction, Appendix",
    });
  });

  it("resets local wizard state when question_id changes", () => {
    const { rerender } = render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion()}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByLabelText("Summary"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Which sections should be included?")).toBeInTheDocument();

    rerender(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({ question_id: "q-2" })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByText("What output format should I use?")).toBeInTheDocument();
    expect(screen.queryByText("Which sections should be included?")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Summary")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("keeps the action area visible by making question content scrollable", () => {
    render(
      <PendingQuestionWizard
        pendingQuestion={makePendingQuestion({
          questions: [
            {
              header: "Long Prompt",
              question: "This is a very long question. ".repeat(120),
              multiSelect: false,
              options: [
                { label: "Continue", description: "Continue processing" },
              ],
            },
          ],
        })}
        answeringQuestion={false}
        error={null}
        onSubmitAnswers={vi.fn()}
      />,
    );

    expect(screen.getByTestId("pending-question-scroll-area")).toHaveClass("overflow-y-auto");
    expect(screen.getByRole("button", { name: "Finish and Submit" })).toBeInTheDocument();
  });
});
