//! Content-coding decoders for captured bodies (RFC 9110 section 8.4).
//!
//! The proxy forwards compressed bytes to the customer unchanged and sends the
//! same bytes here with their `Content-Encoding`, so traces hold readable text.

use std::io::{self, Read};

/// Decoded output larger than this is refused, so a small compressed body
/// cannot expand without bound.
pub const MAX_DECODED_BYTES: usize = 96 * 1024 * 1024;

#[derive(Debug, PartialEq, Eq)]
pub enum Decoded {
    /// Every coding was removed.
    Complete(Vec<u8>),
    /// The input ended or broke mid-stream; this is what decoded before it,
    /// such as a stream the client cancelled.
    Partial(Vec<u8>),
}

#[derive(Debug, PartialEq, Eq, thiserror::Error)]
pub enum DecodeError {
    #[error("unsupported content coding {0}")]
    Unsupported(String),
    #[error("decoded body is larger than {MAX_DECODED_BYTES} bytes")]
    TooLarge,
}

/// Removes `codings`, a `Content-Encoding` value listing the codings in the
/// order they were applied, so they are undone last to first.
pub fn decode(bytes: &[u8], codings: &str) -> Result<Decoded, DecodeError> {
    let mut current = bytes.to_vec();
    let mut partial = false;
    let codings: Vec<String> = codings
        .split(',')
        .map(|coding| coding.trim().to_ascii_lowercase())
        .filter(|coding| !coding.is_empty() && coding != "identity")
        .collect();

    for coding in codings.iter().rev() {
        let (output, complete) = match coding.as_str() {
            "gzip" | "x-gzip" => read(flate2::read::MultiGzDecoder::new(&current[..]))?,
            "deflate" => deflate(&current)?,
            "br" => read(brotli_decompressor::Decompressor::new(&current[..], 4096))?,
            "zstd" => read(
                zstd::stream::read::Decoder::new(&current[..])
                    .map_err(|_| DecodeError::Unsupported(coding.clone()))?,
            )?,
            other => return Err(DecodeError::Unsupported(other.to_owned())),
        };
        partial |= !complete;
        current = output;
    }

    Ok(if partial {
        Decoded::Partial(current)
    } else {
        Decoded::Complete(current)
    })
}

/// HTTP `deflate` is zlib-wrapped, but some servers send raw deflate.
fn deflate(bytes: &[u8]) -> Result<(Vec<u8>, bool), DecodeError> {
    let zlib = read(flate2::read::ZlibDecoder::new(bytes))?;
    if zlib.1 || !zlib.0.is_empty() {
        return Ok(zlib);
    }

    read(flate2::read::DeflateDecoder::new(bytes))
}

/// Reads to the end within the limit; an error keeps what was read before it.
fn read(reader: impl Read) -> Result<(Vec<u8>, bool), DecodeError> {
    let mut limited = reader.take(MAX_DECODED_BYTES as u64 + 1);
    let mut output = Vec::new();
    let mut buffer = [0u8; 64 * 1024];

    loop {
        match limited.read(&mut buffer) {
            Ok(0) => break,
            Ok(read) => {
                output.extend_from_slice(&buffer[..read]);
                if output.len() > MAX_DECODED_BYTES {
                    return Err(DecodeError::TooLarge);
                }
            }
            Err(error) if error.kind() == io::ErrorKind::Interrupted => continue,
            Err(_) => return Ok((output, false)),
        }
    }

    Ok((output, true))
}

#[cfg(test)]
mod tests {
    use std::io::Write;

    use super::*;

    const TEXT: &[u8] =
        b"data: {\"type\":\"message_start\"}\n\ndata: {\"type\":\"message_stop\"}\n\n";

    fn gzip(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = flate2::write::GzEncoder::new(Vec::new(), flate2::Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    fn zlib(bytes: &[u8]) -> Vec<u8> {
        let mut encoder =
            flate2::write::ZlibEncoder::new(Vec::new(), flate2::Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    fn raw_deflate(bytes: &[u8]) -> Vec<u8> {
        let mut encoder =
            flate2::write::DeflateEncoder::new(Vec::new(), flate2::Compression::default());
        encoder.write_all(bytes).unwrap();
        encoder.finish().unwrap()
    }

    fn brotli(bytes: &[u8]) -> Vec<u8> {
        let mut encoder = brotli::CompressorWriter::new(Vec::new(), 4096, 5, 22);
        encoder.write_all(bytes).unwrap();
        encoder.into_inner()
    }

    #[test]
    fn every_supported_coding_round_trips() {
        let zstd = zstd::bulk::compress(TEXT, 3).unwrap();
        for (coding, encoded) in [
            ("gzip", gzip(TEXT)),
            ("x-gzip", gzip(TEXT)),
            ("deflate", zlib(TEXT)),
            ("deflate", raw_deflate(TEXT)),
            ("br", brotli(TEXT)),
            ("zstd", zstd),
            ("identity", TEXT.to_vec()),
            ("GZIP ", gzip(TEXT)),
        ] {
            assert_eq!(
                decode(&encoded, coding),
                Ok(Decoded::Complete(TEXT.to_vec())),
                "{coding}"
            );
        }
    }

    #[test]
    fn stacked_codings_are_undone_last_to_first() {
        let encoded = zstd::bulk::compress(&gzip(TEXT), 3).unwrap();
        assert_eq!(
            decode(&encoded, "gzip, zstd"),
            Ok(Decoded::Complete(TEXT.to_vec()))
        );
    }

    #[test]
    fn a_cut_off_stream_keeps_what_decoded() {
        let long: Vec<u8> = (0..200_000)
            .flat_map(|n: u32| format!("line {n}\n").into_bytes())
            .collect();
        let encoded = gzip(&long);
        let Ok(Decoded::Partial(prefix)) = decode(&encoded[..encoded.len() / 2], "gzip") else {
            panic!("a truncated gzip stream is partial");
        };
        assert!(!prefix.is_empty());
        assert!(long.starts_with(&prefix));
    }

    #[test]
    fn unknown_codings_and_bombs_are_refused() {
        assert_eq!(
            decode(b"x", "compress"),
            Err(DecodeError::Unsupported("compress".to_owned()))
        );
        let bomb = gzip(&vec![0u8; MAX_DECODED_BYTES + 1]);
        assert!(bomb.len() < 1024 * 1024);
        assert_eq!(decode(&bomb, "gzip"), Err(DecodeError::TooLarge));
    }
}
