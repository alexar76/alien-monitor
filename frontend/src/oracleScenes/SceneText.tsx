import { Suspense } from 'react';
import type { ComponentProps } from 'react';
import { Text } from '@react-three/drei';

const font = `${import.meta.env.BASE_URL}fonts/oracle-labels.ttf`;

/** Font loading affects labels only; geometry keeps rendering. */
export default function SceneText(props: ComponentProps<typeof Text>) {
  return <Suspense fallback={null}><Text {...props} font={font} /></Suspense>;
}
