#!/usr/bin/env node
const { program } = require('commander');
const Parser = require('tree-sitter');

program
  .command('analyze <repo>')
  .option('--format <type>', 'output format', 'json')
  .action((repo, opts) => {
    console.log(`Analyzing repository ${repo} as ${opts.format}`);
  });

program
  .command('diff <base> <head>')
  .action((base, head) => {
    console.log(`Computing call-graph diff between ${base} and ${head}`);
  });

program.parse();
