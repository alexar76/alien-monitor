import type { EcoNode } from '../../App';
import NodeSceneSlot from '../../nodeScenes/NodeSceneSlot';
import { hasNodeScene, resolveNodeScene } from '../../nodeScenes/resolve';

/**
 * Back-compat shim — all node previews now resolve through
 * `nodeScenes/resolve.ts` + `NodeSceneSlot`. Prefer importing those directly.
 */
export { hasNodeScene as hasNodeVisual };

interface Props {
  node: EcoNode;
  themeColor: string;
  mobile?: boolean;
  t: (key: string, vars?: Record<string, string | number>, defaultValue?: string) => string;
}

export default function NodeVisual({ node, themeColor, mobile, t }: Props) {
  const scene = resolveNodeScene(node);
  if (!scene || scene.kind === 'oracle') return null;
  return (
    <NodeSceneSlot
      scene={scene}
      node={node}
      themeColor={themeColor}
      mobile={mobile}
      t={t}
    />
  );
}
