// 提取前端 mock 数据为 JSON，供 Python 初始化脚本使用
const fs = require('fs')
const path = require('path')

// 小程序 mock 目录在当前文件的 ../../outfit/miniprogram/mock
const mockDir = path.join(__dirname, '..', '..', 'outfit', 'miniprogram', 'mock')
const items = require(path.join(mockDir, 'items.js'))
const tryon = require(path.join(mockDir, 'tryon.js'))

async function main() {
  const itemsResult = await items.list()
  const presets = await tryon.presets()
  const categories = await tryon.categories()

  const outputPath = path.join(__dirname, 'mock_data.json')
  fs.writeFileSync(
    outputPath,
    JSON.stringify(
      {
        items: itemsResult.list,
        presets,
        categories,
      },
      null,
      2,
    ),
    'utf-8',
  )
  console.log(`mock data written to ${outputPath}`)
}

main().catch((err) => {
  console.error(err)
  process.exit(1)
})
