import { describe, expect, it } from 'vitest';
import { formatUsd } from '../lib/money';

describe('formatUsd', () => {
  it('shows sub-cent prices instead of rounding them to $0.00', () => {
    expect(formatUsd(0.001)).toBe('$0.001');
    expect(formatUsd(0.0059)).toBe('$0.0059');
    expect(formatUsd(0.00001)).toBe('$0.00001');
  });

  it('keeps the half-cent and the tenth of a cent that toFixed rounded away', () => {
    // FactoryAgentsCard printed 0.015 as "$0.01" (toFixed(2) on a binary 0.01499…), and
    // TreasuryCard printed 0.0015 as "$0.00"; both are real spends and balances.
    expect(formatUsd(0.015)).toBe('$0.015');
    expect(formatUsd(0.0015)).toBe('$0.0015');
    expect(formatUsd(0.0135)).toBe('$0.0135');
  });

  it('keeps cents for everyday amounts and trims only past them', () => {
    expect(formatUsd(0.06)).toBe('$0.06');
    expect(formatUsd(0.1234)).toBe('$0.1234');
    expect(formatUsd(12.5)).toBe('$12.50');
    expect(formatUsd(3)).toBe('$3.00');
  });

  it('never prints a positive amount as zero', () => {
    expect(formatUsd(0.0000004)).toBe('<$0.000001');
    expect(formatUsd(0)).toBe('$0.00');
  });

  it('handles sign and garbage', () => {
    expect(formatUsd(-0.002)).toBe('-$0.002');
    expect(formatUsd(Number.NaN)).toBe('$—');
  });
});
