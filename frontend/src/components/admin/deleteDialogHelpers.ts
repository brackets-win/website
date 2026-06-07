import type { Dispatch, SetStateAction } from 'react';

import {
  adminGetDeleteImpact,
  type DeleteImpactRecord,
  type DeleteImpactResource,
} from '../../utils/api';

export type AdminDeleteTarget = {
  id: number;
  label: string;
  relatedRecords: DeleteImpactRecord[];
  loadingRelated: boolean;
};

export type { DeleteImpactResource };

export function startDeleteTarget(
  resource: DeleteImpactResource,
  id: number,
  label: string,
  setTarget: Dispatch<SetStateAction<AdminDeleteTarget | null>>,
): void {
  setTarget({ id, label, relatedRecords: [], loadingRelated: true });
  void adminGetDeleteImpact(resource, id)
    .then(({ related }) => {
      setTarget((prev) =>
        prev?.id === id
          ? { id, label, relatedRecords: related, loadingRelated: false }
          : prev,
      );
    })
    .catch(() => {
      setTarget(null);
    });
}
