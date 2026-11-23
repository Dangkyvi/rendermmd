import { readFile } from 'node:fs/promises';
import { parseFlowchart } from '/app/mermaid-model.mjs';
const {diagram} = await parseFlowchart(await readFile(process.argv[2], 'utf8'));
console.log(JSON.stringify({edges:diagram.db.getEdges(), nodes:[...diagram.db.getVertices().values()], subgraphs:diagram.db.getSubGraphs()}, null, 2));
