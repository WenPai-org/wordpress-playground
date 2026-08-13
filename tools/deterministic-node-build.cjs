'use strict';

const fs = require('node:fs');

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

// Directory enumeration order is filesystem-dependent. Vite/Rollup consume
// that order while discovering modules and assets, so two otherwise identical
// source trees may allocate different chunk names. Sort every public readdir
// result by the raw bytes of its name while retaining strings, Buffers, and
// Dirent instances exactly as Node returned them.
const nameBytes = (entry) => {
  const name = entry && typeof entry === 'object' && 'name' in entry
    ? entry.name
    : entry;
  return Buffer.isBuffer(name) ? name : Buffer.from(name);
};
const sortEntries = (entries) => entries.sort((left, right) =>
  Buffer.compare(nameBytes(left), nameBytes(right))
);

const originalReaddirSync = fs.readdirSync;
fs.readdirSync = function deterministicReaddirSync(path, options) {
  return sortEntries(originalReaddirSync.apply(this, arguments));
};

const originalReaddir = fs.readdir;
fs.readdir = function deterministicReaddir(path, options, callback) {
  const args = Array.from(arguments);
  callback = args[args.length - 1];
  if (typeof callback !== 'function') {
    return originalReaddir.apply(this, args);
  }
  args[args.length - 1] = function deterministicReaddirCallback(error, entries) {
    callback(error, error ? entries : sortEntries(entries));
  };
  return originalReaddir.apply(this, args);
};

const originalPromisesReaddir = fs.promises.readdir;
fs.promises.readdir = function deterministicPromisesReaddir(path, options) {
  return originalPromisesReaddir.apply(this, arguments).then(sortEntries);
};
