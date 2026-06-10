import { useEffect, useRef } from 'react';
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom';

import { listUserBrackets } from '../../utils/api';
import { challengePath } from '../../routes';

/** Rewrites legacy `?ub=` links to `/challenge/:id/bracket?entry=`. */
export function LegacyUbRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams] = useSearchParams();
  const ub = searchParams.get('ub');
  const started = useRef(false);

  useEffect(() => {
    if (started.current || !ub) return;
    const entryId = parseInt(ub, 10);
    if (!Number.isFinite(entryId)) return;
    started.current = true;

    void listUserBrackets().then(({ user_brackets }) => {
      const entry = user_brackets.find((row) => row.id === entryId);
      if (entry?.challenge_id != null) {
        navigate(
          challengePath(entry.challenge_id, 'bracket', { entry: entryId }),
          { replace: true },
        );
        return;
      }

      const next = new URLSearchParams(searchParams);
      next.delete('ub');
      const qs = next.toString();
      navigate(`${location.pathname}${qs ? `?${qs}` : ''}`, { replace: true });
    });
  }, [location.pathname, navigate, searchParams, ub]);

  return null;
}
