Gmail blocks .js files inside attachments, so the three JavaScript files were sent
with a .txt suffix. Restore them before running anything, from inside this folder:

    for f in *.js.txt; do mv "$f" "${f%.txt}"; done

Then: node serve.js  ->  http://localhost:8080
Read HANDOVER.md next. From_sand_to.txt is the prose as a plain document.
