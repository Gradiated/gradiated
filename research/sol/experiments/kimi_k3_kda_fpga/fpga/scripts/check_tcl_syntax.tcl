set failed 0
foreach path $argv {
    set handle [open $path r]
    set source_text [read $handle]
    close $handle
    if {![info complete $source_text]} {
        puts stderr "incomplete Tcl syntax: $path"
        set failed 1
    }
}
exit $failed
