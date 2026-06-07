/** Site mark: closing brace, space, opening brace — same as header / login. */
export function BracketsLogoMark({ className }: { className?: string }) {
  return (
    <span className={className} aria-hidden>
      {'}'} {'{'}
    </span>
  );
}
