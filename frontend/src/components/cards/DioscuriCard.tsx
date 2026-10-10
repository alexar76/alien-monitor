import type { EcoNode } from '../../App';

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
  expandedChild: string | null;
  setExpandedChild: (id: string | null) => void;
}

/* DIOSCURI — twins/collaboration split, plus the community links (twins only;
   THEOROS lives under Collaboration). */
export default function DioscuriCard({ node, themeColor, mobile, t, expandedChild, setExpandedChild }: Props) {
  return (
    <>
      {(node.children?.length || node.collaboration) && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          {node.children && node.children.length > 0 && (
            <>
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
                {t('nodeDetail.dioscuri.twinsTitle')}
              </div>
              <div className="space-y-1">
                {node.children.map((child) => {
                  const isExpanded = expandedChild === child.id;
                  return (
                    <div key={child.id}>
                      <button
                        type="button"
                        onClick={() => setExpandedChild(isExpanded ? null : child.id)}
                        className="w-full px-3 py-1.5 rounded text-xs flex items-center gap-2 transition-colors hover:brightness-110 cursor-pointer text-left"
                        style={{
                          backgroundColor: themeColor + (isExpanded ? '16' : '08'),
                          border: isExpanded ? `1px solid ${themeColor}44` : undefined,
                        }}
                      >
                        <div
                          className="w-1.5 h-1.5 rounded-full shrink-0"
                          style={{ backgroundColor: themeColor, opacity: isExpanded ? 1 : 0.6 }}
                        />
                        <span className="text-white/70">{child.label}</span>
                        <span className="ml-auto text-white/30">{isExpanded ? '▾' : '▸'}</span>
                      </button>
                      {isExpanded && (
                        <div
                          className="mt-1 ml-3 mr-1 px-3 py-2 rounded text-xs"
                          style={{
                            backgroundColor: themeColor + '10',
                            border: `1px solid ${themeColor}28`,
                          }}
                        >
                          <div className="text-white/55 mb-2 leading-relaxed">
                            {child.id === 'castor'
                              ? t('nodeDetail.dioscuri.castorBlurb')
                              : t('nodeDetail.dioscuri.polluxBlurb')}
                          </div>
                          {child.url && (
                            <a
                              href={child.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-mono transition-colors hover:brightness-110"
                              style={{ color: themeColor }}
                            >
                              {child.id === 'castor'
                                ? t('nodeDetail.dioscuri.castorLink')
                                : t('nodeDetail.dioscuri.polluxLink')}{' '}
                              ↗
                            </a>
                          )}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}
          {node.collaboration && (
            <>
              <div
                className="my-3 border-t border-dashed"
                style={{ borderColor: themeColor + '28' }}
              />
              <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-1">
                {t('nodeDetail.dioscuri.collaborationTitle')}
              </div>
              <div className="text-[9px] font-mono text-white/35 mb-2 leading-relaxed">
                {t('nodeDetail.dioscuri.collaborationNote')}
              </div>
              {(() => {
                const collab = node.collaboration!;
                const collabColor = '#4de8ff';
                const isExpanded = expandedChild === collab.id;
                const theorosActive = collab.active === true;
                const statusLabel = theorosActive
                  ? t('nodeDetail.dioscuri.theorosActive')
                  : t('nodeDetail.dioscuri.theorosInactive');
                const statusStyle = theorosActive
                  ? { backgroundColor: '#22c55e22', color: '#86efac' }
                  : { backgroundColor: '#ffffff12', color: '#ffffff55' };
                return (
                  <div>
                    <button
                      type="button"
                      onClick={() => setExpandedChild(isExpanded ? null : collab.id)}
                      className="w-full px-3 py-2 rounded text-xs flex items-center gap-2 transition-colors hover:brightness-110 cursor-pointer text-left"
                      style={{
                        backgroundColor: collabColor + (isExpanded ? '18' : '0c'),
                        border: `1px solid ${collabColor}${isExpanded ? '66' : '33'}`,
                      }}
                    >
                      <span className="text-[10px] font-mono px-1.5 py-0.5 rounded shrink-0"
                        style={{ backgroundColor: collabColor + '22', color: collabColor }}>
                        {t('nodeDetail.dioscuri.collaborationBadge')}
                      </span>
                      <span className="text-white/80 font-medium">{collab.label}</span>
                      <span
                        className="text-[9px] font-mono px-1.5 py-0.5 rounded shrink-0"
                        style={statusStyle}
                      >
                        {statusLabel}
                      </span>
                      <span className="ml-auto text-white/30">{isExpanded ? '▾' : '▸'}</span>
                    </button>
                    {isExpanded && (
                      <div
                        className="mt-1 px-3 py-2 rounded text-xs"
                        style={{
                          backgroundColor: collabColor + '0c',
                          border: `1px solid ${collabColor}33`,
                        }}
                      >
                        <div className="text-white/55 mb-2 leading-relaxed">
                          {t('nodeDetail.dioscuri.theorosBlurb')}
                        </div>
                        <div className="flex flex-col gap-1.5">
                          {collab.url && (
                            <a
                              href={collab.url}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-mono transition-colors hover:brightness-110"
                              style={{ color: collabColor }}
                            >
                              {t('nodeDetail.dioscuri.theorosLanding')} ↗
                            </a>
                          )}
                          {collab.repo && (
                            <a
                              href={collab.repo}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 font-mono text-white/45 hover:text-white/70"
                            >
                              {t('nodeDetail.dioscuri.theorosRepo')} ↗
                            </a>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })()}
            </>
          )}
        </div>
      )}
      {node.community_links && Object.keys(node.community_links).length > 0 && (
        <div className="mb-4" onClick={(e) => e.stopPropagation()}>
          <div className="text-[10px] font-mono uppercase tracking-wider text-white/40 mb-2">
            {t('nodeDetail.community.title')}
          </div>
          <div className="space-y-1.5">
            {node.community_links.telegram && (
              <a
                href={node.community_links.telegram}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('nodeDetail.community.telegramBot')} ↗
              </a>
            )}
            {node.community_links.telegram_channel && (
              <a
                href={node.community_links.telegram_channel}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('nodeDetail.community.telegramChannel')} ↗
              </a>
            )}
            {node.community_links.discord && (
              <a
                href={node.community_links.discord}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('nodeDetail.community.discord')} ↗
              </a>
            )}
            {node.community_links.github && (
              <a
                href={node.community_links.github}
                target="_blank"
                rel="noreferrer"
                className="block px-3 py-2 rounded text-xs font-mono transition-colors hover:brightness-110"
                style={{ backgroundColor: themeColor + '12', border: `1px solid ${themeColor}33`, color: themeColor }}
              >
                {t('nodeDetail.community.github')} ↗
              </a>
            )}
          </div>
        </div>
      )}
    </>
  );
}

