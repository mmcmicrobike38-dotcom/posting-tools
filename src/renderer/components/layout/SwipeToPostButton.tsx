interface SwipeToPostButtonProps {
  disabled: boolean;
  posting: boolean;
  disabledReason?: string;
  onConfirm(): void;
}

export function SwipeToPostButton({ disabled, posting, disabledReason, onConfirm }: SwipeToPostButtonProps) {
  return (
    <section className="side-card swipe-card sidebar-section">
      <div className="sidebar-section-header">
        <div>
          <h3>Posting</h3>
          <p>Send approved records to SCRVSBR.</p>
        </div>
      </div>
      <button
        className="success-action post-button"
        onClick={onConfirm}
        disabled={disabled || posting}
        title={disabled && disabledReason ? disabledReason : "Ctrl+P"}
        aria-label={disabled && disabledReason ? `Post disabled. ${disabledReason}` : "Post validated data"}
      >
        {posting ? "Posting..." : "Post"}
      </button>
      <p className="sidebar-note">{disabled && disabledReason ? disabledReason : "Review the summary before posting."}</p>
    </section>
  );
}
