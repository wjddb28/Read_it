import { useEffect, useRef } from "react";
export default function Modal({ open, close, title, children }) {
  const ref = useRef(null);
  useEffect(() => {
    if (open && !ref.current.open) ref.current.showModal();
    else if (!open && ref.current.open) ref.current.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      className="content-dialog"
      aria-label={title}
      onClose={close}
      onClick={(e) => {
        const r = ref.current.getBoundingClientRect();
        if (
          e.target === ref.current &&
          (e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom)
        )
          close();
      }}
    >
      <div className="dialog-heading">
        <h2>{title}</h2>
        <button
          type="button"
          className="settings-close"
          onClick={close}
          aria-label="창 닫기"
        >
          ×
        </button>
      </div>
      {children}
    </dialog>
  );
}
