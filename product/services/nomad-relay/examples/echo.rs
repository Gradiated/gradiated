// Local integration fixture. Not included in the production image.
use std::io::{Read, Write};
fn main() -> std::io::Result<()> {
    for stream in std::net::TcpListener::bind("127.0.0.1:4647")?.incoming() {
        let mut stream = stream?;
        std::thread::spawn(move || {
            let mut buffer = [0; 4096];
            while let Ok(size) = stream.read(&mut buffer) {
                if size == 0 || stream.write_all(&buffer[..size]).is_err() {
                    break;
                }
            }
        });
    }
    Ok(())
}
