import { useState } from 'react';

type Props = {
  displayName: string;
  imageUrl: string | null | undefined;
  className: string;
  placeholderClassName: string;
};

export function ContestantAvatar({
  displayName,
  imageUrl,
  className,
  placeholderClassName,
}: Props) {
  const [failed, setFailed] = useState(false);

  if (!imageUrl || failed) {
    return (
      <span className={placeholderClassName} aria-hidden>
        {displayName.charAt(0)}
      </span>
    );
  }

  return (
    <img
      className={className}
      src={imageUrl}
      alt=""
      onError={() => setFailed(true)}
    />
  );
}
