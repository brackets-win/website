import { useCallback, useEffect, useMemo, useState } from 'react';
import type {
  BracketContestantInfo,
  BracketGroupPreview,
  BracketStageInfo,
  UserBracketDetail,
} from '../../utils/api';
import { ApiError, patchUserBracketMetadata } from '../../utils/api';
import { ContestantAvatar } from './ContestantAvatar';
import './GroupFixturesPanel.css';

export type GroupFixture = {
  id: string;
  home_id: number;
  away_id: number;
  home_score: number | null;
  away_score: number | null;
};

export type GroupFixturesMap = Record<string, GroupFixture[]>;

type StandingRow = {
  contestant_id: number;
  played: number;
  w: number;
  d: number;
  l: number;
  gf: number;
  ga: number;
  gd: number;
  pts: number;
};

function generateRoundRobin(
  teamIds: number[],
  matchesPerContestant: number,
  groupCode: string,
): GroupFixture[] {
  const n = teamIds.length;
  if (n < 2) return [];
  const double = 2 * (n - 1);
  // Values below home&away count use single RR; >= double uses home and away.
  const useDouble = matchesPerContestant >= double;
  const out: GroupFixture[] = [];
  let idx = 0;
  for (let i = 0; i < n; i += 1) {
    for (let j = i + 1; j < n; j += 1) {
      const a = teamIds[i]!;
      const b = teamIds[j]!;
      out.push({
        id: `${groupCode}-${idx}`,
        home_id: a,
        away_id: b,
        home_score: null,
        away_score: null,
      });
      idx += 1;
      if (useDouble) {
        out.push({
          id: `${groupCode}-${idx}`,
          home_id: b,
          away_id: a,
          home_score: null,
          away_score: null,
        });
        idx += 1;
      }
    }
  }
  return out;
}

function ensureFixtures(
  groups: BracketGroupPreview[],
  existing: GroupFixturesMap | undefined,
  matchesPer: number,
): GroupFixturesMap {
  const out: GroupFixturesMap = {};
  for (const g of groups) {
    const ids = g.teams.map((t) => t.id);
    const generated = generateRoundRobin(ids, matchesPer, g.code);
    const prev = existing?.[g.code];
    if (!prev || prev.length !== generated.length) {
      out[g.code] = generated;
      continue;
    }
    out[g.code] = generated.map((row, i) => {
      const old =
        prev.find(
          (p) => p.home_id === row.home_id && p.away_id === row.away_id,
        ) ?? prev[i];
      return {
        ...row,
        home_score: old?.home_score ?? null,
        away_score: old?.away_score ?? null,
      };
    });
  }
  return out;
}

function standingsForGroup(
  teamIds: number[],
  fixtures: GroupFixture[],
  pointsWin = 3,
  pointsTie = 1,
  pointsLoss = 0,
): StandingRow[] {
  const stats = new Map<number, StandingRow>();
  for (const tid of teamIds) {
    stats.set(tid, {
      contestant_id: tid,
      played: 0,
      w: 0,
      d: 0,
      l: 0,
      gf: 0,
      ga: 0,
      gd: 0,
      pts: 0,
    });
  }
  for (const m of fixtures) {
    if (m.home_score == null || m.away_score == null) continue;
    const home = stats.get(m.home_id);
    const away = stats.get(m.away_id);
    if (!home || !away) continue;
    home.played += 1;
    away.played += 1;
    home.gf += m.home_score;
    home.ga += m.away_score;
    away.gf += m.away_score;
    away.ga += m.home_score;
    if (m.home_score > m.away_score) {
      home.w += 1;
      away.l += 1;
      home.pts += pointsWin;
      away.pts += pointsLoss;
    } else if (m.home_score < m.away_score) {
      away.w += 1;
      home.l += 1;
      away.pts += pointsWin;
      home.pts += pointsLoss;
    } else {
      home.d += 1;
      away.d += 1;
      home.pts += pointsTie;
      away.pts += pointsTie;
    }
  }
  const rows = [...stats.values()].map((r) => ({
    ...r,
    gd: r.gf - r.ga,
  }));
  rows.sort(
    (a, b) =>
      b.pts - a.pts ||
      b.gd - a.gd ||
      b.gf - a.gf ||
      a.contestant_id - b.contestant_id,
  );
  return rows;
}

type Props = {
  userBracketId: number;
  groups: BracketGroupPreview[];
  groupStage: BracketStageInfo;
  initialFixtures?: GroupFixturesMap;
  busy: boolean;
  readOnly?: boolean;
  onSaved: (userBracket?: UserBracketDetail) => void | Promise<void>;
  onError: (msg: string) => void;
};

export function GroupFixturesPanel({
  userBracketId,
  groups,
  groupStage,
  initialFixtures,
  busy,
  readOnly = false,
  onSaved,
  onError,
}: Props) {
  const matchesPer = groupStage.group?.matches_per_contestant ?? 3;
  const pointsWin = groupStage.group?.points_per_win ?? 3;
  const pointsTie = groupStage.group?.points_per_tie ?? 1;
  const pointsLoss = groupStage.group?.points_per_loss ?? 0;

  const [fixtures, setFixtures] = useState<GroupFixturesMap>(() =>
    ensureFixtures(groups, initialFixtures, matchesPer),
  );
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setFixtures(ensureFixtures(groups, initialFixtures, matchesPer));
  }, [groups, initialFixtures, matchesPer]);

  const byId = useMemo(() => {
    const m = new Map<number, BracketContestantInfo>();
    for (const g of groups) {
      for (const t of g.teams) m.set(t.id, t);
    }
    return m;
  }, [groups]);

  const nameOf = useCallback(
    (id: number) => byId.get(id)?.display_name ?? `Team ${id}`,
    [byId],
  );

  const updateScore = (
    code: string,
    fixtureId: string,
    side: 'home' | 'away',
    raw: string,
  ) => {
    const trimmed = raw.trim();
    const val =
      trimmed === ''
        ? null
        : Number.isFinite(Number(trimmed))
          ? Math.max(0, Math.min(99, parseInt(trimmed, 10)))
          : null;
    setFixtures((prev) => ({
      ...prev,
      [code]: (prev[code] ?? []).map((row) => {
        if (row.id !== fixtureId) return row;
        return side === 'home'
          ? { ...row, home_score: val }
          : { ...row, away_score: val };
      }),
    }));
  };

  const save = async () => {
    if (readOnly || busy || saving) return;
    setSaving(true);
    onError('');
    try {
      const { user_bracket } = await patchUserBracketMetadata(userBracketId, {
        group_fixtures: fixtures,
      });
      await onSaved(user_bracket);
    } catch (e) {
      onError(e instanceof ApiError ? e.message : 'Could not save fixtures.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="gfp">
      <div className="gfp__groups">
        {groups.map((g) => {
          const rows = fixtures[g.code] ?? [];
          const table = standingsForGroup(
            g.teams.map((t) => t.id),
            rows,
            pointsWin,
            pointsTie,
            pointsLoss,
          );
          return (
            <section key={g.code} className="gfp__group">
              <h3 className="gfp__group-title">Group {g.code}</h3>
              <div className="gfp__table-wrap">
                <table className="gfp__table">
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">Team</th>
                      <th scope="col">PTS</th>
                      <th scope="col">GD</th>
                      <th scope="col">GS</th>
                      <th scope="col">GC</th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.map((row, i) => {
                      const team = byId.get(row.contestant_id);
                      return (
                        <tr key={row.contestant_id}>
                          <td>{i + 1}</td>
                          <td className="gfp__team">
                            {team ? (
                              <>
                                <ContestantAvatar
                                  displayName={team.display_name}
                                  imageUrl={team.image_url}
                                  className="gfp__avatar"
                                  placeholderClassName="gfp__avatar gfp__avatar--ph"
                                />
                                <span>{team.display_name}</span>
                              </>
                            ) : (
                              nameOf(row.contestant_id)
                            )}
                          </td>
                          <td>{row.pts}</td>
                          <td>{row.gd > 0 ? `+${row.gd}` : row.gd}</td>
                          <td>{row.gf}</td>
                          <td>{row.ga}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              <ul className="gfp__fixtures">
                {rows.map((fx) => (
                  <li key={fx.id} className="gfp__fixture">
                    <span className="gfp__fixture-home">
                      {nameOf(fx.home_id)}
                    </span>
                    <div className="gfp__fixture-scores">
                      <input
                        className="gfp__score"
                        inputMode="numeric"
                        maxLength={2}
                        value={fx.home_score ?? ''}
                        disabled={readOnly || busy || saving}
                        aria-label={`${nameOf(fx.home_id)} score`}
                        onChange={(e) =>
                          updateScore(g.code, fx.id, 'home', e.target.value)
                        }
                      />
                      <span className="gfp__score-sep">–</span>
                      <input
                        className="gfp__score"
                        inputMode="numeric"
                        maxLength={2}
                        value={fx.away_score ?? ''}
                        disabled={readOnly || busy || saving}
                        aria-label={`${nameOf(fx.away_id)} score`}
                        onChange={(e) =>
                          updateScore(g.code, fx.id, 'away', e.target.value)
                        }
                      />
                    </div>
                    <span className="gfp__fixture-away">
                      {nameOf(fx.away_id)}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      {!readOnly ? (
        <button
          type="button"
          className="btn btn--primary"
          disabled={busy || saving}
          onClick={() => void save()}
        >
          {saving ? 'Saving…' : 'Save Results'}
        </button>
      ) : null}
    </div>
  );
}
