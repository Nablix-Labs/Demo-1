import PageShell, { Chip, Avatar } from '@/components/PageShell';

interface Person {
  name: string;
  role: 'Tutor' | 'Student' | 'Parent';
  detail: string;
  online: boolean;
}

const PEOPLE: Person[] = [
  { name: 'Numera AI', role: 'Tutor', detail: 'Your AI maths tutor · always on', online: true },
  { name: 'Ms Priya Sharma', role: 'Tutor', detail: 'Algebra & Number · human tutor', online: true },
  { name: 'Aïsha Khan', role: 'Student', detail: 'Year 9 · study group', online: true },
  { name: 'Liam OConnor', role: 'Student', detail: 'Year 9 · study group', online: false },
  { name: 'Wei Chen', role: 'Student', detail: 'Year 10 · study group', online: false },
  { name: 'Fatima Noor', role: 'Parent', detail: 'Guardian · progress reports', online: false },
];

export default function PeoplePage() {
  return (
    <PageShell
      title="People"
      subtitle="Tutors, classmates and guardians connected to your account."
    >
      <div className="rounded-lg border border-[#c8c8c8] divide-y divide-[#eaeaea] overflow-hidden">
        {PEOPLE.map((p) => (
          <div key={p.name} className="flex items-center gap-4 px-5 py-4 hover:bg-[#f9f9f9] transition-colors">
            <div className="relative">
              <Avatar name={p.name} />
              <span
                className={`absolute -right-0.5 -bottom-0.5 w-3 h-3 rounded-full border-2 border-white ${
                  p.online ? 'bg-[#1a1a1a]' : 'bg-[#c8c8c8]'
                }`}
                aria-label={p.online ? 'Online' : 'Offline'}
              />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[14px] font-semibold text-[#1a1a1a]">{p.name}</div>
              <div className="text-[12px] text-[#7a7a7a] truncate">{p.detail}</div>
            </div>
            <Chip tone={p.role === 'Tutor' ? 'solid' : 'outline'}>{p.role}</Chip>
          </div>
        ))}
      </div>
    </PageShell>
  );
}
