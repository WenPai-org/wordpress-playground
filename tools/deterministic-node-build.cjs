'use strict';

// Vite 5 derives temporary dependency-cache suffixes and parser sentinels from
// pid, wall-clock time, and Math.random(). Those values can change module IDs
// and, in turn, Rollup chunk/minifier ordering. Release builds run serially, so
// a fixed per-process identity is safe and makes those bookkeeping values a
// deterministic function of SOURCE_DATE_EPOCH.
const epoch = Number.parseInt(process.env.SOURCE_DATE_EPOCH || '', 10);
if (!Number.isSafeInteger(epoch) || epoch <= 0) {
  throw new Error('SOURCE_DATE_EPOCH must be a positive integer');
}
Object.defineProperty(process, 'pid', { value: 4242, configurable: true });
Date.now = () => epoch * 1000;
let state = (epoch ^ 0x9e3779b9) >>> 0;
Math.random = () => {
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  return (state >>> 0) / 0x100000000;
};
