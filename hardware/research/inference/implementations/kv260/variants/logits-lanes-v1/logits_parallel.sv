// Parallel rows of the final 320-by-32 score projection.
module logits_parallel #(
    parameter integer LANES = 2,
    parameter integer RESULT_BITS = 32
) (
    input logic clk, reset,
    input logic input_valid,
    output logic input_ready,
    input logic [7:0] input_address,
    input logic signed [15:0] input_value,
    input logic weight_valid,
    output logic weight_ready,
    input logic [8:0] weight_row,
    input logic [7:0] weight_address,
    input logic signed [15:0] weight_value,
    input logic start,
    output logic start_ready, busy,
    output logic result_valid,
    input logic result_ready,
    output logic signed [RESULT_BITS-1:0] result,
    output logic [8:0] result_row,
    output logic saturated
);
    localparam integer GROUPS = 320 / LANES;
    localparam integer LANE_BITS = $clog2(LANES);
    localparam integer GROUP_BITS = $clog2(GROUPS);
    localparam logic signed [47:0] RESULT_MAX = (48'sd1 << (RESULT_BITS-1)) - 48'sd1;
    localparam logic signed [47:0] RESULT_MIN = -(48'sd1 << (RESULT_BITS-1));

    typedef enum logic [2:0] {IDLE, PRIME, MAC, ROUND, STREAM} state_t;
    state_t state;
    logic [GROUP_BITS-1:0] group_index;
    logic [LANE_BITS-1:0] output_lane;
    logic [4:0] coordinate, read_coordinate;
    logic signed [15:0] input_memory [0:31], input_operand;
    logic signed [RESULT_BITS-1:0] scores [0:LANES-1];
    logic clips [0:LANES-1];
    logic advance_mac, read_pair, launch, last_lane, last_group, next_group;
    logic [GROUP_BITS+4:0] read_weight_address, write_weight_address;

    assign input_ready = state == IDLE && !start && input_address < 32;
    assign weight_ready = state == IDLE && !start && weight_row < 320 && weight_address < 32;
    assign start_ready = state == IDLE && !input_valid && !weight_valid;
    assign busy = state != IDLE;
    assign result_valid = state == STREAM;
    assign result_row = {group_index, output_lane};
    assign result = scores[output_lane];
    assign saturated = clips[output_lane];

    assign advance_mac = state == MAC && coordinate != 31;
    assign read_pair = state == PRIME || advance_mac;
    assign read_coordinate = coordinate + 5'(advance_mac);
    assign read_weight_address = {group_index, read_coordinate};
    assign write_weight_address = {weight_row[8:LANE_BITS], weight_address[4:0]};
    assign launch = start && start_ready;
    assign last_lane = output_lane == LANE_BITS'(LANES-1);
    assign last_group = group_index == GROUP_BITS'(GROUPS-1);
    assign next_group = result_valid && result_ready && last_lane && !last_group;

    always_ff @(posedge clk) begin
        if (!reset && input_valid && input_ready)
            input_memory[input_address[4:0]] <= input_value;
        if (reset)
            input_operand <= 0;
        else if (read_pair)
            input_operand <= input_memory[read_coordinate];
    end

    // Consecutive output rows use different banks. Each bank gets one read
    // address and the same activation is broadcast to every lane.
    for (genvar lane = 0; lane < LANES; ++lane) begin : bank
        (* ram_style = "block" *) logic signed [15:0] weights [0:GROUPS*32-1];
        logic signed [15:0] weight_operand;
        (* keep = "true", use_dsp = "yes" *) logic signed [31:0] product;
        (* use_dsp = "no" *) logic signed [47:0] next_sum;
        logic signed [47:0] accumulator, rounded;

        assign product = input_operand * weight_operand;
        assign next_sum = accumulator + {{16{product[31]}}, product};
        always_comb begin
            rounded = accumulator >>> 8;
            if (accumulator[7:0] > 8'h80 || (accumulator[7:0] == 8'h80 && rounded[0]))
                rounded = rounded + 48'sd1;
        end

        always_ff @(posedge clk) begin
            if (!reset && weight_valid && weight_ready && weight_row[LANE_BITS-1:0] == LANE_BITS'(lane))
                weights[write_weight_address] <= weight_value;

            if (reset) begin
                weight_operand <= 0;
                accumulator <= 0;
                scores[lane] <= 0;
                clips[lane] <= 0;
            end else begin
                if (read_pair)
                    weight_operand <= weights[read_weight_address];
                if (launch || next_group)
                    accumulator <= 0;
                else if (state == MAC)
                    accumulator <= next_sum;

                if (state == ROUND) begin
                    if (rounded > RESULT_MAX) begin
                        scores[lane] <= RESULT_BITS'(RESULT_MAX);
                        clips[lane] <= 1;
                    end else if (rounded < RESULT_MIN) begin
                        scores[lane] <= RESULT_BITS'(RESULT_MIN);
                        clips[lane] <= 1;
                    end else begin
                        scores[lane] <= RESULT_BITS'(rounded);
                        clips[lane] <= 0;
                    end
                end
            end
        end
    end

    always_ff @(posedge clk) begin
        if (reset) begin
            state <= IDLE;
            coordinate <= 0;
            group_index <= 0;
            output_lane <= 0;
        end else begin
            case (state)
                IDLE: if (launch) begin
                    group_index <= 0;
                    coordinate <= 0;
                    state <= PRIME;
                end
                PRIME: state <= MAC;
                MAC: if (advance_mac)
                    coordinate <= read_coordinate;
                else
                    state <= ROUND;
                ROUND: begin
                    output_lane <= 0;
                    state <= STREAM;
                end
                STREAM: if (result_ready) begin
                    if (!last_lane)
                        output_lane <= output_lane + 1'b1;
                    else if (last_group)
                        state <= IDLE;
                    else begin
                        group_index <= group_index + 1'b1;
                        coordinate <= 0;
                        state <= PRIME;
                    end
                end
                default: state <= IDLE;
            endcase
        end
    end
endmodule
