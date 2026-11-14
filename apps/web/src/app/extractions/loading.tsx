import "../../styles/extraction.css";

export default function LoadingExtraction() {
  return (
    <p role="status" aria-busy="true" className="extraction-loading">
      Loading extraction view…
    </p>
  );
}
