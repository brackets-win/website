import type { BracketStageInfo } from '../../utils/api';

import { AdminNumberInput } from './AdminNumberInput';
import './admin-shared.css';

const KNOCKOUT_FILL_OPTIONS = [
  { value: 'standard', label: 'Standard' },
  { value: 'seeding', label: 'Seeding' },
  { value: 'mapping', label: 'Mapping' },
] as const;

type KnockoutFillMethod = (typeof KNOCKOUT_FILL_OPTIONS)[number]['value'];

function readKnockoutFillMethod(metadata: unknown): KnockoutFillMethod {
  if (
    metadata &&
    typeof metadata === 'object' &&
    'knockout_fill_method' in metadata
  ) {
    const raw = (metadata as { knockout_fill_method?: unknown })
      .knockout_fill_method;
    if (typeof raw === 'string') {
      const v = raw.trim().toLowerCase();
      if (KNOCKOUT_FILL_OPTIONS.some((o) => o.value === v)) {
        return v as KnockoutFillMethod;
      }
    }
  }
  return 'standard';
}

function setKnockoutFillMethod(
  metadata: unknown,
  method: KnockoutFillMethod,
): Record<string, unknown> {
  const base =
    metadata && typeof metadata === 'object' && !Array.isArray(metadata)
      ? { ...(metadata as Record<string, unknown>) }
      : {};
  base.knockout_fill_method = method;
  return base;
}

type Props = {
  stage: BracketStageInfo;
  onChange: (stage: BracketStageInfo) => void;
  disabled?: boolean;
  isFirstKnockout?: boolean;
  /** Group → knockout fill only applies when a group stage exists. */
  hasGroupStage?: boolean;
};

function metadataText(value: unknown): string {
  if (value == null) return '';
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return '';
  }
}

function parseMetadataInput(text: string): unknown {
  const t = text.trim();
  if (!t) return null;
  return JSON.parse(t) as unknown;
}

export function BracketStageEditor({
  stage,
  onChange,
  disabled,
  isFirstKnockout = false,
  hasGroupStage = false,
}: Props) {
  const isGroup = stage.stage_type === 'GROUP';
  const isKo = stage.stage_type === 'KNOCKOUT';
  const isThirdPlace = stage.knockout?.is_third_place === true;

  return (
    <fieldset className="stage-editor">
      <legend>
        {stage.name}{' '}
        <span className="stage-editor__meta">
          #{stage.order} · {stage.stage_type.toLowerCase()}
        </span>
      </legend>

      <div className="field">
        <label>Stage name</label>
        <input
          className="input"
          value={stage.name}
          onChange={(e) => onChange({ ...stage, name: e.target.value })}
          disabled={disabled}
        />
      </div>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={stage.is_random_draw}
          onChange={(e) =>
            onChange({ ...stage, is_random_draw: e.target.checked })
          }
          disabled={disabled}
        />
        Random draw for this stage
      </label>

      {isGroup && stage.group ? (
        <div className="stage-editor__block">
          <h4 className="stage-editor__subtitle">Group stage rules</h4>
          <div className="form-grid form-grid--2">
            <div className="field">
              <label>Number of groups</label>
              <AdminNumberInput
                value={stage.group.number_of_groups}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      number_of_groups: Math.max(1, n),
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Qualifiers per group</label>
              <AdminNumberInput
                value={stage.group.contestants_qualifying_per_group}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      contestants_qualifying_per_group: Math.max(1, n),
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Matches per team</label>
              <AdminNumberInput
                value={stage.group.matches_per_contestant}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      matches_per_contestant: Math.max(1, n),
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Remaining spots strategy</label>
              <select
                className="select"
                value={stage.group.remaining_spots_strategy ?? ''}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      remaining_spots_strategy: e.target.value || null,
                    },
                  })
                }
                disabled={disabled}
              >
                <option value="">None</option>
                <option value="HighestPlaceWithinGroup">Highest place in group</option>
                <option value="MostPointsAcrossGroups">Most points across groups</option>
              </select>
            </div>
            <div className="field">
              <label>Group position picking</label>
              <select
                className="select"
                value={stage.group.group_position_picking ?? 'all'}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      group_position_picking:
                        e.target.value === 'qualifying_only'
                          ? 'qualifying_only'
                          : 'all',
                    },
                  })
                }
                disabled={disabled}
              >
                <option value="all">All</option>
                <option value="qualifying_only">Qualifying Only</option>
              </select>
            </div>
            <div className="field">
              <label>Points per exact position</label>
              <AdminNumberInput
                value={stage.group.points_per_exact_position ?? 0}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_exact_position: n,
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per advancer</label>
              <AdminNumberInput
                value={stage.group.points_per_advancer ?? 0}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_advancer: n,
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per win</label>
              <AdminNumberInput
                value={stage.group.points_per_win}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_win: n,
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per tie</label>
              <AdminNumberInput
                value={stage.group.points_per_tie}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_tie: n,
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Points per loss</label>
              <AdminNumberInput
                value={stage.group.points_per_loss}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    group: {
                      ...stage.group!,
                      points_per_loss: n,
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.group.ties_allowed}
              onChange={(e) =>
                onChange({
                  ...stage,
                  group: { ...stage.group!, ties_allowed: e.target.checked },
                })
              }
              disabled={disabled}
            />
            Ties allowed
          </label>
        </div>
      ) : null}

      {isKo && stage.knockout && !isThirdPlace ? (
        <div className="stage-editor__block">
          <h4 className="stage-editor__subtitle">Knockout rules</h4>
          <div className="form-grid form-grid--2">
            <div className="field">
              <label>Points per team in round</label>
              <AdminNumberInput
                value={stage.points_per_correct_pick}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({ ...stage, points_per_correct_pick: n });
                }}
                disabled={disabled}
              />
            </div>
            <div className="field">
              <label>Number of legs</label>
              <AdminNumberInput
                value={stage.knockout.number_of_legs}
                onChange={(n) => {
                  if (n === null) return;
                  onChange({
                    ...stage,
                    knockout: {
                      ...stage.knockout!,
                      number_of_legs: Math.max(1, n),
                    },
                  });
                }}
                disabled={disabled}
              />
            </div>
          </div>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.has_extra_time}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    has_extra_time: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Extra time
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.has_penalty_shootout}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    has_penalty_shootout: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Penalty shootout
          </label>
          <label className="checkbox-row">
            <input
              type="checkbox"
              checked={stage.knockout.is_final}
              onChange={(e) =>
                onChange({
                  ...stage,
                  knockout: {
                    ...stage.knockout!,
                    is_final: e.target.checked,
                  },
                })
              }
              disabled={disabled}
            />
            Final
          </label>
          {isFirstKnockout && hasGroupStage ? (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={
                  stage.knockout.combine_points_with_group_stage !== false
                }
                onChange={(e) =>
                  onChange({
                    ...stage,
                    knockout: {
                      ...stage.knockout!,
                      combine_points_with_group_stage: e.target.checked,
                    },
                  })
                }
                disabled={disabled}
              />
              Combine points with group stage
            </label>
          ) : null}
          {isFirstKnockout && hasGroupStage ? (
            <div className="field" style={{ marginTop: '0.75rem' }}>
              <label htmlFor={`ko-fill-${stage.id}`}>
                Group → knockout fill
              </label>
              <select
                id={`ko-fill-${stage.id}`}
                className="select"
                value={readKnockoutFillMethod(stage.metadata)}
                onChange={(e) =>
                  onChange({
                    ...stage,
                    metadata: setKnockoutFillMethod(
                      stage.metadata,
                      e.target.value as KnockoutFillMethod,
                    ),
                  })
                }
                disabled={disabled}
              >
                {KNOCKOUT_FILL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          ) : null}
        </div>
      ) : null}

      <div className="field">
        <label>Stage metadata (JSON)</label>
        <textarea
          className="textarea textarea--mono"
          rows={3}
          defaultValue={metadataText(stage.metadata)}
          key={`meta-${stage.id}-${metadataText(stage.metadata).length}`}
          onBlur={(e) => {
            try {
              const metadata = parseMetadataInput(e.target.value);
              onChange({ ...stage, metadata });
            } catch {
              /* keep previous until valid */
            }
          }}
          disabled={disabled}
          placeholder='{"group_knockout_mapping": …}'
          spellCheck={false}
        />
      </div>
    </fieldset>
  );
}
