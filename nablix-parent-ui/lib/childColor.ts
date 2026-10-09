/**
 * A colour per child, fixed by their position in the family list, so a sibling
 * is recognisable at a glance on every screen (avatar, family card, report).
 */
export interface ChildLook {
  /** Avatar fill + text. */
  avatar: string;
  /** Family-card hero block. */
  hero: string;
  /** The wave under the hero. */
  wave: string;
}

const LOOKS: ChildLook[] = [
  { avatar: 'bg-mustard text-ink', hero: 'bg-teal', wave: '#F4B63F' },
  { avatar: 'bg-coral text-white', hero: 'bg-coral', wave: '#3D8C79' },
  { avatar: 'bg-info text-white', hero: 'bg-info', wave: '#F7C9D2' },
  { avatar: 'bg-teal text-white', hero: 'bg-teal-deep', wave: '#FBE3A9' },
];

export const childLook = (index: number): ChildLook => LOOKS[Math.max(0, index) % LOOKS.length];
