import { useEffect, useRef, useState } from 'react';

type Props = {
  value: number | null;
  onChange: (value: number | null) => void;
  disabled?: boolean;
  invalid?: boolean;
  id?: string;
  className?: string;
};

function formatValue(value: number | null): string {
  return value == null ? '' : String(value);
}

export function AdminNumberInput({
  value,
  onChange,
  disabled,
  invalid = false,
  id,
  className = 'input',
}: Props) {
  const [text, setText] = useState(() => formatValue(value));
  const focusedRef = useRef(false);

  useEffect(() => {
    if (!focusedRef.current) {
      setText(formatValue(value));
    }
  }, [value]);

  const classNames = [className, invalid ? 'input--invalid' : '']
    .filter(Boolean)
    .join(' ');

  return (
    <input
      id={id}
      className={classNames}
      inputMode="numeric"
      pattern="[0-9]*"
      value={text}
      disabled={disabled}
      onFocus={() => {
        focusedRef.current = true;
      }}
      onBlur={() => {
        focusedRef.current = false;
      }}
      onChange={(e) => {
        const raw = e.target.value.replace(/\D/g, '');
        setText(raw);
        if (raw === '') {
          onChange(null);
          return;
        }
        const n = parseInt(raw, 10);
        if (!Number.isNaN(n)) {
          onChange(n);
        }
      }}
    />
  );
}
