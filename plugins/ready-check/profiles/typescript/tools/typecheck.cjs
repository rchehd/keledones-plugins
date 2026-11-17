const path = require('node:path');
const ts = require(process.argv[2]);
const config = process.argv[3];
const diagnostics = [];
const files = new Set();
const outputs = new Map();
const directories = new Set();

const canonical = file => {
  const normalized = ts.sys.resolvePath(file);
  return ts.sys.useCaseSensitiveFileNames ? normalized : normalized.toLowerCase();
};

const system = {
  ...ts.sys,
  fileExists: file => outputs.has(canonical(file)) || ts.sys.fileExists(file),
  readFile: file => outputs.get(canonical(file)) ?? ts.sys.readFile(file),
  directoryExists: dir => directories.has(canonical(dir)) || ts.sys.directoryExists(dir),
  createDirectory: dir => directories.add(canonical(dir)),
  writeFile: (file, text) => {
    const key = canonical(file);
    outputs.set(key, text);
    for (let dir = path.dirname(key); !directories.has(dir); dir = path.dirname(dir)) {
      directories.add(dir);
      if (dir === path.dirname(dir)) break;
    }
  },
  deleteFile: file => outputs.delete(canonical(file)),
  setModifiedTime: () => {},
};

const host = ts.createSolutionBuilderHost(system, undefined, item => {
  const { file, start, code, messageText } = item;
  const line = file && start !== undefined ? file.getLineAndCharacterOfPosition(start).line + 1 : 0;
  diagnostics.push({
    file: file?.fileName ?? config,
    line,
    code,
    message: ts.flattenDiagnosticMessageText(messageText, '\n'),
  });
});
host.afterProgramEmitAndDiagnostics = builder => {
  for (const file of builder.getProgram().getSourceFiles()) {
    files.add(path.resolve(file.fileName));
  }
};
const status = ts.createSolutionBuilder(host, [config], { force: true }).build();
process.stdout.write(JSON.stringify({ status, diagnostics, files: [...files] }));
