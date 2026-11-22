// Observation only. Include inside the pinned autonomous_core_tb.
localparam int N2_WAIT_PHASE = 12, FF_START_PHASE = 13, FF_WAIT_PHASE = 14;
localparam int FIRST_PAIR = 1, FIRST_SEND = 2, LAST_WAIT = 13, DOWN_RUN = 16;
localparam int DENSE_OUTPUT = 4, SCALAR_OUTPUT = 1, DIV_STEP = 2, DIV_FINISH = 17;

int profile_file, profile_positions;
int prepare_ticks[6]; // N2_WAIT, input transfer, input blocked, FF_START, launch, launch blocked
int ff_ticks[17], activity[17][16], dense_ticks[3][5], dense_io[3][2];
int command_io[6][4], scalar_ticks[6][18], exp_div[3][3]; // step, finish, entry
longint signed observed_min[6][3], observed_max[6][3];
int pending_command = -1, previous_scalar_state, invalid_ticks, parent_results;
string profile_path;

task automatic reset_profile_position;
    foreach (prepare_ticks[i]) prepare_ticks[i] = 0;
    foreach (ff_ticks[i]) ff_ticks[i] = 0;
    foreach (activity[i,j]) activity[i][j] = 0;
    foreach (dense_ticks[i,j]) dense_ticks[i][j] = 0;
    foreach (dense_io[i,j]) dense_io[i][j] = 0;
    foreach (command_io[i,j]) command_io[i][j] = 0;
    foreach (scalar_ticks[i,j]) scalar_ticks[i][j] = 0;
    foreach (exp_div[i,j]) exp_div[i][j] = 0;
    parent_results = 0;
    invalid_ticks = 0;
endtask

initial begin
    profile_positions = 0;
    reset_profile_position();
    if (!$value$plusargs("FF_PROFILE=%s", profile_path)) $fatal(1, "Missing feed-forward profile path");
    profile_file = $fopen(profile_path, "w");
    if (!profile_file) $fatal(1, "Cannot open feed-forward profile");
end

function automatic bit dense_arithmetic(input int state_code);
    return state_code inside {[1:3]}; // READ, MAC, ROUND
endfunction

task automatic profile_dense(input int unit, state_code, input bit valid, ready);
    if (state_code < 0 || state_code > DENSE_OUTPUT || valid != (state_code == DENSE_OUTPUT))
        $fatal(1, "Unexpected dense state/valid: %0d/%0d", unit, state_code);
    dense_ticks[unit][state_code]++;
    if (valid) dense_io[unit][ready ? 0 : 1]++;
endtask

task automatic observe_args(input int operation, input longint signed a, b, shift);
    longint signed operands[3];
    operands = '{a, b, shift};
    foreach (operands[i]) begin
        if (command_io[operation][0] == 0 || operands[i] < observed_min[operation][i])
            observed_min[operation][i] = operands[i];
        if (command_io[operation][0] == 0 || operands[i] > observed_max[operation][i])
            observed_max[operation][i] = operands[i];
    end
endtask

task automatic profile_scalar(input int ff_state, scalar_state);
    int operation, expected_opcode, division;
    operation = (ff_state - FIRST_SEND) / 2;
    if (ff_state[0] == 1'b0) begin
        case (operation)
            0: expected_opcode = 3; // exponential
            1: expected_opcode = 1; // sigmoid division
            2, 4: expected_opcode = 2; // multiply
            default: expected_opcode = 0; // rounded shift
        endcase
        if (!dut.core.ff.sc_valid || int'(dut.core.ff.sc_op) != expected_opcode || pending_command != -1)
            $fatal(1, "Unexpected scalar command before acceptance: %0d", operation);
        if (dut.core.ff.sc_ready) begin
            observe_args(operation, dut.core.ff.sc_a, dut.core.ff.sc_b, longint'(dut.core.ff.sc_shift));
            command_io[operation][0]++;
            pending_command = operation;
            previous_scalar_state = -1;
        end else begin
            command_io[operation][1]++;
        end
    end else begin
        if (pending_command != operation || scalar_state < 0 || scalar_state >= 18)
            $fatal(1, "Unpaired scalar response state %0d for %0d", scalar_state, operation);
        scalar_ticks[operation][scalar_state]++;
        if (operation == 0 && scalar_state inside {DIV_STEP, DIV_FINISH}) begin
            case (int'(dut.core.ff.scalar.return_state))
                5: division = 0; // EXP_POWER
                6: division = 1; // EXP_INDEX
                10: division = 2; // EXP_DONE
                default: $fatal(1, "Unknown return from exponential division");
            endcase
            if (dut.core.ff.scalar.denominator != 64'd45426)
                $fatal(1, "Unexpected exponential divisor");
            exp_div[division][scalar_state == DIV_STEP ? 0 : 1]++;
            if (scalar_state == DIV_STEP && previous_scalar_state != DIV_STEP)
                exp_div[division][2]++;
        end
        previous_scalar_state = scalar_state;
        if (dut.core.ff.sc_result_valid) begin
            if (scalar_state != SCALAR_OUTPUT || dut.core.ff.sc_error)
                $fatal(1, "Unexpected scalar result status");
            if (dut.core.ff.sc_result_ready) begin
                command_io[operation][2]++;
                pending_command = -1;
            end else begin
                command_io[operation][3]++;
            end
        end
    end
endtask

task automatic dump_profile_position;
    if (pending_command != -1) $fatal(1, "Incomplete scalar command in position");
    profile_positions++;
    if (int'(dut.core_context_count) != profile_positions)
        $fatal(1, "Unexpected context position for feed-forward output");

    $fwrite(profile_file, "POSITION %0d %0d %0d\n", profile_positions, parent_results, invalid_ticks);
    $fwrite(profile_file, "PREPARE");
    foreach (prepare_ticks[i]) $fwrite(profile_file, " %0d", prepare_ticks[i]);
    $fwrite(profile_file, "\nPARENT");
    foreach (ff_ticks[i]) $fwrite(profile_file, " %0d", ff_ticks[i]);
    $fwrite(profile_file, "\nACTIVITY");
    foreach (activity[i,j]) $fwrite(profile_file, " %0d", activity[i][j]);
    $fwrite(profile_file, "\nDENSE");
    foreach (dense_ticks[i,j]) $fwrite(profile_file, " %0d", dense_ticks[i][j]);
    $fwrite(profile_file, "\nDENSE_IO");
    foreach (dense_io[i,j]) $fwrite(profile_file, " %0d", dense_io[i][j]);
    $fwrite(profile_file, "\nCOMMAND_IO");
    foreach (command_io[i,j]) $fwrite(profile_file, " %0d", command_io[i][j]);
    $fwrite(profile_file, "\nSCALAR");
    foreach (scalar_ticks[i,j]) $fwrite(profile_file, " %0d", scalar_ticks[i][j]);
    $fwrite(profile_file, "\nEXP_DIV");
    foreach (exp_div[i,j]) $fwrite(profile_file, " %0d", exp_div[i][j]);
    $fwrite(profile_file, "\nARGS_MIN");
    foreach (observed_min[i,j]) $fwrite(profile_file, " %0d", observed_min[i][j]);
    $fwrite(profile_file, "\nARGS_MAX");
    foreach (observed_max[i,j]) $fwrite(profile_file, " %0d", observed_max[i][j]);
    $fwrite(profile_file, "\n");

    reset_profile_position();
endtask

always @(posedge aclk) if (aresetn && observing) begin : profile_feedforward
    int ff_state, gate_state, up_state, down_state, scalar_state;
    logic [3:0] active;
    if (int'(dut.core_phase) == N2_WAIT_PHASE) begin
        prepare_ticks[0]++;
        if (dut.core.ff.input_valid) prepare_ticks[dut.core.ff.input_ready ? 1 : 2]++;
    end
    if (int'(dut.core_phase) == FF_START_PHASE) begin
        prepare_ticks[3]++;
        prepare_ticks[dut.core.ff.launch ? 4 : 5]++;
    end
    if (int'(dut.core_phase) == FF_WAIT_PHASE) begin
        ff_state = int'(dut.core.ff.state);
        if (ff_state < FIRST_PAIR || ff_state > DOWN_RUN) begin
            invalid_ticks++;
            $fatal(1, "FF_WAIT contains invalid parent state %0d, invalid count %0d", ff_state, invalid_ticks);
        end
        ff_ticks[ff_state]++;
        gate_state = int'(dut.core.ff.gate_dense.state);
        up_state = int'(dut.core.ff.up_dense.state);
        down_state = int'(dut.core.ff.down_dense.state);
        scalar_state = int'(dut.core.ff.scalar.state);
        profile_dense(0, gate_state, dut.core.ff.g_valid, dut.core.ff.g_ready);
        profile_dense(1, up_state, dut.core.ff.u_valid, dut.core.ff.u_ready);
        profile_dense(2, down_state, dut.core.ff.d_valid, dut.core.ff.d_ready);
        active = {scalar_state > SCALAR_OUTPUT, dense_arithmetic(down_state),
                  dense_arithmetic(up_state), dense_arithmetic(gate_state)};
        activity[ff_state][active]++;
        if (ff_state inside {[FIRST_SEND:LAST_WAIT]}) profile_scalar(ff_state, scalar_state);
        else if (scalar_state != 0) $fatal(1, "Scalar active outside its registered parent window");
        if (dut.core.ff.result_valid && dut.core.ff.result_ready) begin
            parent_results++;
            if (dut.core.ff.result_row == 9'd31) dump_profile_position();
        end
    end
end

final $fclose(profile_file);
