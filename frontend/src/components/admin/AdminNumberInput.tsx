import { useEffect, useState } from 'react';

type Props = {
  value: number;
  onChange: (value: number) => void;
  disabled?: boolean;
  id?: string;
  className?: string;
};

export function AdminNumberInput({
  value,
  onChange,
  disabled,
  id,
  className = 'input',
}: Props) {
  const [text, setText] = useState(String(value));

  useEffect(() => {
    setText(String(value));
  }, [value]);

  return (
    <input
      id={id}
      className={className}
      inputMode="numeric"
      pattern="[0-9]*"
      value={text}
      disabled={disabled}
      onChange={(e) => {
        const raw = e.target.value.replace(/\D/g, '');
        setText(raw);
        if (raw === '') {
          return;
        }
        const n = parseInt(raw, 10);
        if (!Number.isNaN(n)) {
          onChange(n);
        }
      }}
      onBlur={() => {
        if (text === '') {
          onChange(0);
          setText('0');
        } else {
          setText(String(value));
        }
      }}
    />
  );
}
