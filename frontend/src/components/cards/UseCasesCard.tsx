import type { EcoNode } from '../../App';

/** Rich body for Use Cases Portal — boards / wedges under the 3D globe slot. */
export default function UseCasesCard({
  node,
  themeColor,
  t,
}: {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}) {
  const boards = [
    t('nodeDetail.useCases.boardPhysical', undefined, 'Physical oracle'),
    t('nodeDetail.useCases.boardMarket', undefined, 'Marketplace'),
    t('nodeDetail.useCases.boardSafety', undefined, 'Agent safety'),
    t('nodeDetail.useCases.boardVerify', undefined, 'Verify'),
    t('nodeDetail.useCases.boardFactory', undefined, 'Factory'),
    t('nodeDetail.useCases.boardOracles', undefined, 'Math oracles'),
    t('nodeDetail.useCases.boardOps', undefined, 'Ops loop'),
  ];

  return (
    <div className="mb-4 space-y-3" onClick={(e) => e.stopPropagation()}>
      <div className="text-[10px] font-mono uppercase tracking-wider text-white/40">
        {t('nodeDetail.useCases.boards', undefined, 'Direction boards')}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {boards.map((b) => (
          <span
            key={b}
            className="px-2 py-0.5 rounded text-[10px] font-mono"
            style={{
              border: `1px solid ${themeColor}44`,
              color: themeColor,
              background: `${themeColor}12`,
            }}
          >
            {b}
          </span>
        ))}
      </div>
      <p className="text-[11px] text-white/55 leading-relaxed">
        {t(
          'nodeDetail.useCases.blurb',
          undefined,
          'Seven directions · twelve wedges — live rails for attested IoT, pay-per-call agents, and thin products on Hub.',
        )}
      </p>
      {node.url && (
        <a
          href={node.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs font-semibold"
          style={{ color: themeColor }}
        >
          {t('nodeDetail.useCases.open', undefined, 'Open use-cases portal')} →
        </a>
      )}
    </div>
  );
}
