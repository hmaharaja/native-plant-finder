const { statSync } = require("node:fs");
const { resolve } = require("node:path");

const PLANT_IMAGE_INDEX_PATH = resolve(
  __dirname,
  "../public/data/app_data/plant_images/index.json"
);
const PLANT_IMAGE_INDEX_MAX_BYTES = 10 * 1024 * 1024;

function checkSize(path, maxBytes) {
  const { size } = statSync(path);
  if (size > maxBytes) {
    throw new Error(
      `Plant image runtime index is ${size} bytes, exceeding the ${maxBytes} byte limit. ` +
        "Revisit bucketed or per-ecoregion runtime loading before deploying a larger index."
    );
  }
  return size;
}

try {
  const size = checkSize(PLANT_IMAGE_INDEX_PATH, PLANT_IMAGE_INDEX_MAX_BYTES);
  console.log(`plant_image_index_bytes=${size}`);
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
