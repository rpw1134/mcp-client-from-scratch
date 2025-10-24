const Converter = require("openapi-to-postmanv2");
const fs = require("fs");

const openApiData = fs.readFileSync("openapi.json", "utf8");

Converter.convert(
  { type: "json", data: JSON.parse(openApiData) },
  {},
  (err, conversionResult) => {
    if (err) {
      console.error("Conversion failed:", err);
      return;
    }

    if (conversionResult.result) {
      fs.writeFileSync(
        "postman_collection.json",
        JSON.stringify(conversionResult.output[0].data, null, 2)
      );
      console.log("Postman collection generated!");
    }
  }
);
