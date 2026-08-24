require 'fileutils'
require 'cgi'

ROOT = File.expand_path('..', __dir__)
CONTENT_DIR = File.join(ROOT, 'content', 'notes')
NOTES_DIR = File.join(ROOT, 'notes')

def escape(text)
  CGI.escapeHTML(text)
end

def inline_markdown(text)
  escape(text).gsub(/_([^_]+)_/, '<em>\\1</em>').gsub(/\*\*([^*]+)\*\*/, '<strong>\\1</strong>')
end

def render_markdown(markdown)
  blocks = markdown.strip.split(/\n{2,}/)
  blocks.map do |block|
    lines = block.lines.map(&:chomp)
    if lines.first.start_with?('# ')
      "<h1>#{inline_markdown(lines.first[2..])}</h1>"
    elsif lines.first.start_with?('## ')
      "<h2>#{inline_markdown(lines.first[3..])}</h2>"
    elsif lines.all? { |line| line.start_with?('* ') }
      "<ul>#{lines.map { |line| "<li>#{inline_markdown(line[2..])}</li>" }.join}</ul>"
    else
      "<p>#{inline_markdown(lines.join(' '))}</p>"
    end
  end.join("\n")
end

def shell(title, body)
  <<~HTML
    <!doctype html>
    <html lang="en"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>#{escape(title)} — Gradiated</title><link rel="stylesheet" href="/styles.css"/></head>
    <body><div class="page-shell"><header class="nav"><a class="wordmark" href="/">gradiated</a></header>#{body}<footer><a href="/">Gradiated</a><span>© 2026 Gradiated, Inc.</span><a href="/privacy/">Privacy</a></footer></div><script src="/theme.js"></script></body></html>
  HTML
end

posts = Dir.glob(File.join(CONTENT_DIR, '*.md')).map do |file|
  raw = File.read(file, encoding: 'UTF-8')
  front, markdown = raw.match(/\A---\n(.*?)\n---\n(.*)\z/m).captures
  meta = front.lines.to_h { |line| line.strip.split(/:\s+/, 2) }
  { slug: File.basename(file, '.md'), meta: meta, html: render_markdown(markdown) }
end.sort_by { |post| post[:meta]['date'] || '' }.reverse

FileUtils.mkdir_p(NOTES_DIR)
posts.each do |post|
  output_dir = File.join(NOTES_DIR, post[:slug])
  FileUtils.mkdir_p(output_dir)
  article = <<~HTML
    <main class="article"><a class="eyebrow" href="/notes/">← Notes</a><p class="article-date">#{escape(post[:meta]['date'] || '')}</p>#{post[:html]}</main>
  HTML
  File.write(File.join(output_dir, 'index.html'), shell(post[:meta]['title'] || post[:slug], article))
end

rows = posts.map do |post|
  meta = post[:meta]
  "<a class=\"post-row\" href=\"/notes/#{post[:slug]}/\"><span>#{escape(meta['date'] || '')}</span><div><h2>#{escape(meta['title'] || post[:slug])}</h2><p>#{escape(meta['description'] || '')}</p></div><b>↗</b></a>"
end.join
index = "<main class=\"notes\"><h1>Ideas from the edge of inference.</h1><div class=\"post-list\">#{rows}</div></main>"
File.write(File.join(NOTES_DIR, 'index.html'), shell('Notes', index))
