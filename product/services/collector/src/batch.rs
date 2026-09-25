use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    time::Instant,
};

use chrono::{DateTime, NaiveDateTime, Utc};
use uuid::Uuid;

use crate::record::StreamKey;

const COMPRESSION_LEVEL: i32 = 3;
const HOUR_FORMAT: &str = "%Y%m%d%H";

pub struct Batch {
    pub path: PathBuf,
    pub bytes: u64,
    pub opened: Instant,
    file: File,
}

impl Batch {
    pub fn create(directory: &Path, key: &StreamKey) -> io::Result<Self> {
        let path = directory.join(file_name(key, Uuid::now_v7()));
        let file = OpenOptions::new()
            .create_new(true)
            .append(true)
            .open(&path)?;

        Ok(Self {
            path,
            bytes: 0,
            opened: Instant::now(),
            file,
        })
    }

    pub fn append(&mut self, frame: &[u8]) -> io::Result<()> {
        if let Err(error) = self.file.write_all(frame) {
            let _ = self.file.set_len(self.bytes);
            return Err(error);
        }
        self.bytes += frame.len() as u64;

        Ok(())
    }
}

pub fn compress(record: &[u8]) -> io::Result<Vec<u8>> {
    let mut line = Vec::with_capacity(record.len() + 1);
    line.extend_from_slice(record);
    line.push(b'\n');

    zstd::bulk::compress(&line, COMPRESSION_LEVEL)
}

pub struct Frame {
    pub offset: u64,
    pub length: u64,
    pub record: Vec<u8>,
}

/// Stops at the first incomplete or corrupt frame.
pub fn frames(data: &[u8]) -> impl Iterator<Item = Frame> + '_ {
    let mut offset = 0;

    std::iter::from_fn(move || {
        let rest = &data[offset..];
        let length = zstd::zstd_safe::find_frame_compressed_size(rest).ok()?;
        let mut record = zstd::stream::decode_all(rest.get(..length)?).ok()?;
        if record.pop() != Some(b'\n') {
            return None;
        }

        let frame = Frame {
            offset: offset as u64,
            length: length as u64,
            record,
        };
        offset += length;

        Some(frame)
    })
}

pub fn truncate_torn_tail(path: &Path) -> io::Result<u64> {
    let data = fs::read(path)?;
    let complete = frames(&data)
        .last()
        .map_or(0, |frame| frame.offset + frame.length);

    if complete < data.len() as u64 {
        OpenOptions::new()
            .write(true)
            .open(path)?
            .set_len(complete)?;
    }

    Ok(complete)
}

pub fn file_name(key: &StreamKey, batch_id: Uuid) -> String {
    format!(
        "{}.{}.{}.{}.{}.{batch_id}.zst",
        key.workspace_id,
        key.task_key,
        key.hour.format(HOUR_FORMAT),
        key.retention_days,
        key.trainable,
    )
}

pub fn parse_file_name(name: &str) -> Option<(StreamKey, Uuid)> {
    let mut parts = name.strip_suffix(".zst")?.split('.');
    let workspace_id = parts.next()?.parse().ok()?;
    let task_key = parts.next()?.to_owned();
    let hour =
        NaiveDateTime::parse_from_str(&format!("{}0000", parts.next()?), "%Y%m%d%H%M%S").ok()?;
    let retention_days = parts.next()?.parse().ok()?;
    let trainable = parts.next()?.parse().ok()?;
    let batch_id = parts.next()?.parse().ok()?;

    if parts.next().is_some() {
        return None;
    }

    Some((
        StreamKey {
            workspace_id,
            task_key,
            hour: DateTime::<Utc>::from_naive_utc_and_offset(hour, Utc),
            retention_days,
            trainable,
        },
        batch_id,
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::record::generation_hour;

    fn key() -> StreamKey {
        StreamKey {
            workspace_id: Uuid::now_v7(),
            task_key: "support-triage".to_owned(),
            hour: generation_hour(Uuid::now_v7()),
            retention_days: 90,
            trainable: false,
        }
    }

    #[test]
    fn frames_round_trip_and_split_on_their_boundaries() {
        let records: Vec<Vec<u8>> = (0..3)
            .map(|i| format!("{{\"n\":{i}}}").into_bytes())
            .collect();
        let data: Vec<u8> = records
            .iter()
            .flat_map(|record| compress(record).unwrap())
            .collect();

        let frames: Vec<Frame> = frames(&data).collect();

        assert_eq!(frames.len(), 3);
        assert_eq!(
            frames.last().map(|frame| frame.offset + frame.length),
            Some(data.len() as u64)
        );
        for (frame, record) in frames.iter().zip(&records) {
            assert_eq!(&frame.record, record);
        }
        assert_eq!(
            zstd::stream::decode_all(&data[..]).unwrap(),
            b"{\"n\":0}\n{\"n\":1}\n{\"n\":2}\n"
        );
    }

    #[test]
    fn a_torn_final_frame_is_cut_off() {
        let directory = tempfile::tempdir().unwrap();
        let mut batch = Batch::create(directory.path(), &key()).unwrap();
        let whole = compress(b"{\"n\":1}").unwrap();
        batch.append(&whole).unwrap();
        batch.append(&compress(b"{\"n\":2}").unwrap()[..5]).unwrap();

        let complete = truncate_torn_tail(&batch.path).unwrap();

        assert_eq!(complete, whole.len() as u64);
        assert_eq!(fs::read(&batch.path).unwrap(), whole);
    }

    #[test]
    fn file_names_carry_the_stream_key() {
        let key = key();
        let batch_id = Uuid::now_v7();

        assert_eq!(
            parse_file_name(&file_name(&key, batch_id)),
            Some((key, batch_id))
        );
        assert_eq!(parse_file_name("not-a-batch.zst"), None);
    }
}
