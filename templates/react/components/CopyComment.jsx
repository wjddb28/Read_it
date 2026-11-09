import { useState } from 'react';
export default function CopyComment({ text }) {
  const [message, setMessage] = useState('');
  async function copy() {
    try {
      if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
      else {
        const field = document.createElement('textarea');
        field.value = text; field.style.position = 'fixed'; field.style.opacity = '0';
        document.body.appendChild(field); field.select();
        const copied = document.execCommand('copy'); field.remove();
        if (!copied) throw new Error();
      }
      setMessage('복사했어요. 커뮤니티 글쓰기에서 붙여넣어주세요.');
    } catch { setMessage('복사하지 못했어요. 내용을 선택해 직접 복사해주세요.'); }
  }
  return <div className="copy-comment"><button type="button" className="copy-comment-text" onClick={copy} title="클릭해서 코멘트 복사">{text}</button><small>클릭하면 복사돼요</small><p role="status">{message}</p></div>;
}
