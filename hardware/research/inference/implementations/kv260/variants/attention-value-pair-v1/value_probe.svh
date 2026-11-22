        // Bad paired response tags and coordinates must fail closed.
        for(int fault=0;fault<2;fault++) begin
            case_id=-4;prepare(0,1);launch();
            while(dut.state!=5'd13) begin tick();@(negedge clk);end
            corrupt_pair=fault==0;corrupt_coord=fault==1;
            while(!result_valid) begin tick();@(negedge clk);end
            if(!error || result!=0 || step_pair_valid)
                $fatal(1,"Bad paired tag or coordinate produced a usable result");
            corrupt_pair=0;corrupt_coord=0;
            result_ready=1;tick();@(negedge clk);quiet();
        end
        // The even result was consumed and its mate still awaits rounding.
        case_id=-4;prepare(0,1);launch();
        while(!result_valid) begin tick();@(negedge clk);end
        if(error || result_index!=0 || dut.second_accumulator==0)
            $fatal(1,"Missing live mate result before reset");
        result_ready=1;tick();@(negedge clk);
        if(dut.state!=5'd15 || dut.coordinate!=1)
            $fatal(1,"Reset probe missed odd coordinate rounding launch");
        clear();run_case(0,-5);
        $display("PASS paired value tag, coordinate, pending odd result reset and recovery");
