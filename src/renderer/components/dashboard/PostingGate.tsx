interface PostingGateProps {
  reasons: string[];
  expanded: boolean;
  onToggle(): void;
}

export function PostingGate({ reasons, expanded, onToggle }: PostingGateProps) {
  if (!reasons.length) return null;
  const [headline, ...details] = reasons;
  const hasDetails = details.length > 0;

  return (
    <section className="errors posting-gate">
      <div className="posting-gate-header">
        <div>
          <h3>Posting Locked</h3>
          <p>{headline}</p>
        </div>
        {hasDetails ? (
          <button className="see-more-button" onClick={onToggle}>
            {expanded ? "Hide details" : "See more"}
          </button>
        ) : null}
      </div>
      {expanded && hasDetails ? (
        <div className="posting-gate-details">
          {details.map((reason) => <p key={reason}>{reason}</p>)}
        </div>
      ) : null}
    </section>
  );
}
