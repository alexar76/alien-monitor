/**
 * Dollar amounts as the market actually prices them.
 *
 * Capabilities cost fractions of a cent — a weather read is $0.001, the measured average is
 * $0.0059 — so `toFixed(2)` printed every one of them as "$0.00", and the activity stream
 * showed paid calls as free. Precision now follows the size of the number: cents for
 * dollars, four places under a dollar, six under a cent (the credits ledger's own unit is
 * 1/1000 of a cent, so nothing it can charge is lost). Trailing zeros past the cents are
 * trimmed, so $0.06 stays $0.06 rather than $0.0600.
 */
export function formatUsd(amount: number): string {
  if (!Number.isFinite(amount)) return '$—';
  const abs = Math.abs(amount);
  const digits = abs >= 1 ? 2 : abs >= 0.01 ? 4 : 6;
  const fixed = abs.toFixed(digits).replace(/(\.\d{2}\d*?)0+$/, '$1');
  if (abs > 0 && Number(fixed) === 0) return `${amount < 0 ? '-' : ''}<$0.000001`;
  return `${amount < 0 ? '-' : ''}$${fixed}`;
}
