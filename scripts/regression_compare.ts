import { parseWithPythonBackend } from "../src/backend/bridge/pythonBridge";
import { SimsoftWorkflow } from "../src/backend/workflow/simsoftWorkflow";

async function main() {
  const filePath = process.argv[2];
  if (!filePath) {
    throw new Error("Usage: tsx scripts/regression_compare.ts <simsoft.xlsx>");
  }

  const workflow = new SimsoftWorkflow();
  const directPython = await parseWithPythonBackend(filePath);
  const workflowResult = await workflow.parseSimsoftFile(filePath);

  const directPythonJson = JSON.stringify({ rows: directPython.rows, errors: directPython.errors, summary: directPython.summary });
  const workflowJson = JSON.stringify({ rows: workflowResult.rows, errors: workflowResult.errors, summary: workflowResult.summary });
  if (directPythonJson !== workflowJson) {
    throw new Error("Workflow output differs from direct Python backend output.");
  }
  console.log(`Regression comparison passed for ${filePath}`);
  workflow.close();
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
