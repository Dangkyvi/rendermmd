import { readFile } from 'node:fs/promises';
import { parseFlowchart } from '/app/mermaid-model.mjs';
const {diagram, config} = await parseFlowchart(await readFile(process.argv[2], 'utf8'));
console.log(JSON.stringify({parsed:{diagramType:diagram.type},config,title:diagram.db.getDiagramTitle(),nodes:[...diagram.db.getVertices().values()],groups:diagram.db.getSubGraphs(),classes:[...diagram.db.getClasses().entries()],data:diagram.db.getData()},null,2));
