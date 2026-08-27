`timescale 1ns/1ps

module kda_core #(
    parameter integer HEAD_DIM = 128,
    parameter integer LANES = 16,
    parameter integer STATE_W = 24,
    parameter integer STATE_FRAC = 18,
    parameter integer VECTOR_FRAC = 6,
    parameter integer GATE_FRAC = 8
) (
    input  wire                    clk,
    input  wire                    rst_n,
    input  wire                    start,
    input  wire                    clear_state,
    input  wire                    cfg_wr_en,
    input  wire [2:0]              cfg_wr_kind,
    input  wire [15:0]             cfg_wr_addr,
    input  wire [31:0]             cfg_wr_data,
    input  wire [15:0]             out_rd_addr,
    output wire [31:0]             out_rd_data,
    output reg                     busy,
    output reg                     done,
    output reg  [31:0]             cycles
);
    localparam integer ROW_GROUPS = HEAD_DIM / LANES;
    localparam integer STATE_DEPTH = HEAD_DIM * ROW_GROUPS;
    localparam integer GROUP_W = (ROW_GROUPS <= 1) ? 1 : $clog2(ROW_GROUPS);
    localparam integer COL_W = (HEAD_DIM <= 1) ? 1 : $clog2(HEAD_DIM);
    localparam integer STATE_ADDR_W = (STATE_DEPTH <= 1) ? 1 : $clog2(STATE_DEPTH);

    localparam [2:0] CFG_Q = 3'd0;
    localparam [2:0] CFG_K = 3'd1;
    localparam [2:0] CFG_V = 3'd2;
    localparam [2:0] CFG_ALPHA = 3'd3;
    localparam [2:0] CFG_BETA = 3'd4;

    localparam [3:0] ST_IDLE = 4'd0;
    localparam [3:0] ST_CLEAR = 4'd1;
    localparam [3:0] ST_DOT_READ = 4'd2;
    localparam [3:0] ST_DOT_SCALE = 4'd3;
    localparam [3:0] ST_DOT_ACCUMULATE = 4'd4;
    localparam [3:0] ST_UPDATE_READ = 4'd5;
    localparam [3:0] ST_UPDATE_SCALE = 4'd6;
    localparam [3:0] ST_UPDATE_APPLY = 4'd7;
    localparam [3:0] ST_UPDATE_WRITE = 4'd8;

    reg signed [7:0] q_mem [0:HEAD_DIM-1];
    reg signed [7:0] k_mem [0:HEAD_DIM-1];
    reg signed [7:0] v_mem [0:HEAD_DIM-1];
    reg        [7:0] alpha_mem [0:HEAD_DIM-1];
    reg        [7:0] beta_reg;
    reg signed [31:0] output_mem [0:HEAD_DIM-1];

    wire signed [STATE_W-1:0] state_read [0:LANES-1];
    reg signed [STATE_W-1:0] scaled_pipeline [0:LANES-1];
    reg signed [STATE_W-1:0] next_state_pipeline [0:LANES-1];
    reg signed [16:0] gate_key_pipeline [0:LANES-1];
    reg state_write_en;
    reg [STATE_ADDR_W-1:0] state_read_addr;
    reg [STATE_ADDR_W-1:0] state_write_addr;
    reg signed [STATE_W-1:0] state_write_data [0:LANES-1];

    reg [3:0] state;
    reg [COL_W-1:0] column_index;
    reg [GROUP_W-1:0] group_index;
    reg [STATE_ADDR_W-1:0] clear_index;
    reg signed [63:0] dot_accumulator;
    reg signed [63:0] projection_value;
    reg signed [63:0] output_accumulator;

    reg signed [63:0] dot_lane_sum;
    reg signed [63:0] output_lane_sum;
    reg signed [63:0] delta_value;
    reg signed [STATE_W-1:0] scaled_state_comb [0:LANES-1];
    reg signed [STATE_W-1:0] next_state_comb [0:LANES-1];
    reg signed [63:0] scaled_work;
    reg signed [63:0] update_work;
    reg signed [63:0] gate_key_work;

    integer lane;
    integer reset_index;
    genvar bank;

    initial begin
        if (HEAD_DIM < 1 || LANES < 1 || (HEAD_DIM % LANES) != 0) begin
            $error("HEAD_DIM must be positive and divisible by LANES");
        end
        if (STATE_FRAC < VECTOR_FRAC) begin
            $error("STATE_FRAC must be at least VECTOR_FRAC");
        end
    end

    function automatic signed [STATE_W-1:0] saturate_state;
        input signed [63:0] value;
        reg signed [63:0] maximum;
        reg signed [63:0] minimum;
        begin
            maximum = (64'sd1 <<< (STATE_W - 1)) - 1;
            minimum = -(64'sd1 <<< (STATE_W - 1));
            if (value > maximum)
                saturate_state = maximum[STATE_W-1:0];
            else if (value < minimum)
                saturate_state = minimum[STATE_W-1:0];
            else
                saturate_state = value[STATE_W-1:0];
        end
    endfunction

    function automatic signed [31:0] saturate_output;
        input signed [63:0] value;
        begin
            if (value > 64'sh000000007fffffff)
                saturate_output = 32'sh7fffffff;
            else if (value < -64'sh0000000080000000)
                saturate_output = -32'sh80000000;
            else
                saturate_output = value[31:0];
        end
    endfunction

    assign out_rd_data = (out_rd_addr < HEAD_DIM) ? output_mem[out_rd_addr] : 32'd0;

    generate
        for (bank = 0; bank < LANES; bank = bank + 1) begin : state_banks
            kda_state_bank #(
                .WIDTH(STATE_W),
                .DEPTH(STATE_DEPTH),
                .ADDR_W(STATE_ADDR_W)
            ) state_bank (
                .clk(clk),
                .read_addr(state_read_addr),
                .read_data(state_read[bank]),
                .write_en(state_write_en),
                .write_addr(state_write_addr),
                .write_data(state_write_data[bank])
            );
        end
    endgenerate

    always @* begin
        dot_lane_sum = 64'sd0;
        output_lane_sum = 64'sd0;
        delta_value = $signed(v_mem[column_index]);
        delta_value = (delta_value <<< (STATE_FRAC - VECTOR_FRAC)) - projection_value;
        scaled_work = 64'sd0;
        update_work = 64'sd0;
        gate_key_work = 64'sd0;
        for (lane = 0; lane < LANES; lane = lane + 1) begin
            scaled_work = $signed(state_read[lane]) * $signed({1'b0, alpha_mem[group_index * LANES + lane]});
            scaled_state_comb[lane] = saturate_state(scaled_work >>> GATE_FRAC);
            dot_lane_sum = dot_lane_sum + $signed(k_mem[group_index * LANES + lane]) * $signed(scaled_pipeline[lane]);

            gate_key_work = $signed(gate_key_pipeline[lane]);
            update_work = (gate_key_work * delta_value) >>> (GATE_FRAC + VECTOR_FRAC);
            next_state_comb[lane] = saturate_state($signed(scaled_pipeline[lane]) + update_work);
            output_lane_sum = output_lane_sum + $signed(q_mem[group_index * LANES + lane]) * $signed(next_state_pipeline[lane]);
        end
    end

    always @* begin
        state_read_addr = column_index * ROW_GROUPS + group_index;
        state_write_addr = state_read_addr;
        state_write_en = 1'b0;
        for (lane = 0; lane < LANES; lane = lane + 1)
            state_write_data[lane] = next_state_pipeline[lane];
        if (busy && state == ST_CLEAR) begin
            state_write_en = 1'b1;
            state_write_addr = clear_index;
            for (lane = 0; lane < LANES; lane = lane + 1)
                state_write_data[lane] = {STATE_W{1'b0}};
        end else if (busy && state == ST_UPDATE_WRITE) begin
            state_write_en = 1'b1;
        end
    end

    always @(posedge clk) begin
        if (!rst_n) begin
            busy <= 1'b0;
            done <= 1'b0;
            cycles <= 32'd0;
            state <= ST_IDLE;
            column_index <= {COL_W{1'b0}};
            group_index <= {GROUP_W{1'b0}};
            clear_index <= {STATE_ADDR_W{1'b0}};
            dot_accumulator <= 64'sd0;
            projection_value <= 64'sd0;
            output_accumulator <= 64'sd0;
            beta_reg <= 8'd0;
            for (reset_index = 0; reset_index < HEAD_DIM; reset_index = reset_index + 1) begin
                q_mem[reset_index] <= 8'sd0;
                k_mem[reset_index] <= 8'sd0;
                v_mem[reset_index] <= 8'sd0;
                alpha_mem[reset_index] <= 8'd0;
                output_mem[reset_index] <= 32'sd0;
            end
        end else begin
            if (cfg_wr_en && !busy) begin
                case (cfg_wr_kind)
                    CFG_Q: if (cfg_wr_addr < HEAD_DIM) q_mem[cfg_wr_addr] <= cfg_wr_data[7:0];
                    CFG_K: if (cfg_wr_addr < HEAD_DIM) k_mem[cfg_wr_addr] <= cfg_wr_data[7:0];
                    CFG_V: if (cfg_wr_addr < HEAD_DIM) v_mem[cfg_wr_addr] <= cfg_wr_data[7:0];
                    CFG_ALPHA: if (cfg_wr_addr < HEAD_DIM) alpha_mem[cfg_wr_addr] <= cfg_wr_data[7:0];
                    CFG_BETA: beta_reg <= cfg_wr_data[7:0];
                    default: beta_reg <= beta_reg;
                endcase
            end

            if (!busy) begin
                if (clear_state) begin
                    busy <= 1'b1;
                    done <= 1'b0;
                    cycles <= 32'd0;
                    clear_index <= {STATE_ADDR_W{1'b0}};
                    state <= ST_CLEAR;
                end else if (start) begin
                    busy <= 1'b1;
                    done <= 1'b0;
                    cycles <= 32'd0;
                    column_index <= {COL_W{1'b0}};
                    group_index <= {GROUP_W{1'b0}};
                    dot_accumulator <= 64'sd0;
                    projection_value <= 64'sd0;
                    output_accumulator <= 64'sd0;
                    state <= ST_DOT_READ;
                end
            end else begin
                cycles <= cycles + 1'b1;
                case (state)
                    ST_CLEAR: begin
                        if (clear_index == STATE_DEPTH - 1) begin
                            busy <= 1'b0;
                            done <= 1'b1;
                            state <= ST_IDLE;
                        end else begin
                            clear_index <= clear_index + 1'b1;
                        end
                    end

                    ST_DOT_READ: begin
                        state <= ST_DOT_SCALE;
                    end

                    ST_DOT_SCALE: begin
                        for (lane = 0; lane < LANES; lane = lane + 1)
                            scaled_pipeline[lane] <= scaled_state_comb[lane];
                        state <= ST_DOT_ACCUMULATE;
                    end

                    ST_DOT_ACCUMULATE: begin
                        if (group_index == ROW_GROUPS - 1) begin
                            projection_value <= (dot_accumulator + dot_lane_sum) >>> VECTOR_FRAC;
                            dot_accumulator <= 64'sd0;
                            group_index <= {GROUP_W{1'b0}};
                            output_accumulator <= 64'sd0;
                            state <= ST_UPDATE_READ;
                        end else begin
                            dot_accumulator <= dot_accumulator + dot_lane_sum;
                            group_index <= group_index + 1'b1;
                            state <= ST_DOT_READ;
                        end
                    end

                    ST_UPDATE_READ: begin
                        state <= ST_UPDATE_SCALE;
                    end

                    ST_UPDATE_SCALE: begin
                        for (lane = 0; lane < LANES; lane = lane + 1) begin
                            scaled_pipeline[lane] <= scaled_state_comb[lane];
                            gate_key_pipeline[lane] <= $signed({1'b0, beta_reg}) * $signed(k_mem[group_index * LANES + lane]);
                        end
                        state <= ST_UPDATE_APPLY;
                    end

                    ST_UPDATE_APPLY: begin
                        for (lane = 0; lane < LANES; lane = lane + 1)
                            next_state_pipeline[lane] <= next_state_comb[lane];
                        state <= ST_UPDATE_WRITE;
                    end

                    ST_UPDATE_WRITE: begin
                        if (group_index == ROW_GROUPS - 1) begin
                            output_mem[column_index] <= saturate_output((output_accumulator + output_lane_sum) >>> VECTOR_FRAC);
                            group_index <= {GROUP_W{1'b0}};
                            output_accumulator <= 64'sd0;
                            dot_accumulator <= 64'sd0;
                            if (column_index == HEAD_DIM - 1) begin
                                busy <= 1'b0;
                                done <= 1'b1;
                                state <= ST_IDLE;
                            end else begin
                                column_index <= column_index + 1'b1;
                                state <= ST_DOT_READ;
                            end
                        end else begin
                            output_accumulator <= output_accumulator + output_lane_sum;
                            group_index <= group_index + 1'b1;
                            state <= ST_UPDATE_READ;
                        end
                    end

                    default: begin
                        busy <= 1'b0;
                        state <= ST_IDLE;
                    end
                endcase
            end
        end
    end
endmodule
