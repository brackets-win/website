import { useState } from 'react';

type Props = {
  code: string;
  label?: string;
};

export function CopyJoinCode({ code, label = 'Join code' }: Props) {
  const [copied, setCopied] = useState(false);

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="copy-join-code">
      <span className="copy-join-code__label">{label}</span>
      <div className="copy-join-code__row">
        <code className="copy-join-code__value">{code}</code>
        <button type="button" className="btn btn--secondary" onClick={() => void onCopy()}>
          {copied ? 'Copied' : 'Copy'}
        </button>
      </div>
    </div>
  );
}
