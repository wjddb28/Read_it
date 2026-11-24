import Modal from "./Modal";

export default function DeleteConfirmation({ open, busy, onCancel, onDelete, error }) {
  function cancel() {
    if (!busy) onCancel();
  }

  return (
    <Modal open={open} close={cancel} title="삭제하시겠습니까?" size="delete-confirm" showClose={false}>
      <div className="delete-confirm-actions">
        <button type="button" className="danger-btn" disabled={busy} onClick={onDelete}>예</button>
        <button type="button" className="outline-btn" disabled={busy} onClick={cancel} autoFocus>아니오</button>
      </div>
      {error && <p role="alert">{error}</p>}
    </Modal>
  );
}
