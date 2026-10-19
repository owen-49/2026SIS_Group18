import { describeAIError } from "../data/aiErrors";
import { openAISettings } from "../data/aiSettings";

export function AIErrorMessage({ message }: { message: string }) {
  const error = describeAIError(message);
  return (
    <>
      {error ? (
        <>
          <span>
            {error.message} <small>({error.code})</small>
          </span>{" "}
          <button
            type="button"
            className="button button-secondary"
            onClick={openAISettings}
          >
            Open AI settings
          </button>
        </>
      ) : (
        message
      )}
    </>
  );
}
