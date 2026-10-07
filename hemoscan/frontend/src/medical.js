// ABO / Rh red-cell compatibility: a donor is compatible when every antigen on the donor's cells
// is also present in the recipient (otherwise the recipient has antibodies against it).
const antigens = (g) => ({ A: g.startsWith('A'), B: g.includes('B'), Rh: g.endsWith('+') })

export const GROUP_LIST = ['O-', 'O+', 'A-', 'A+', 'B-', 'B+', 'AB-', 'AB+']

export function canDonateTo(donor) {
  const d = antigens(donor)
  return GROUP_LIST.filter((r) => {
    const x = antigens(r)
    return (!d.A || x.A) && (!d.B || x.B) && (!d.Rh || x.Rh)
  })
}

export function canReceiveFrom(recipient) {
  return GROUP_LIST.filter((d) => canDonateTo(d).includes(recipient))
}

export const ageBand = (a) => (a == null ? '' : a < 1 ? 'Infant' : a < 13 ? 'Child' : a < 18 ? 'Adolescent' : a < 65 ? 'Adult' : 'Senior')
