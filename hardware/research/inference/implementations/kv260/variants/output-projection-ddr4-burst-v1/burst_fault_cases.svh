    integer injected_fault = 0;
    task automatic await_transport(input bit return_phase);
        integer clocks_started;
        clocks_started = 0;
        while (!(return_phase ? m_axi_rready : m_axi_arvalid)) begin
            tick();
            if (++clocks_started > 100000) $fatal(1,"Never reached intended outstanding state");
        end
    endtask

    task automatic qualify_fault;
        logic [31:0] status;
        bit timeout_case, cancel_case, still_pending;
        integer initial_beats, expected_drain_beats;
        timeout_case = injected_fault == 4 || injected_fault == 5;
        cancel_case = injected_fault == 6 || injected_fault == 7 || injected_fault == 9 || injected_fault == 10;
        still_pending = injected_fault != 1 && injected_fault != 10;
        hold_ar = injected_fault == 4 || injected_fault == 6;
        hold_r = injected_fault == 5 || injected_fault == 7;
        inject_bad_resp = injected_fault == 1;
        inject_wrong_id = injected_fault == 2;
        inject_early_last = injected_fault == 3;
        inject_late_last = injected_fault == 8;
        initial_beats = injected_fault==1 || injected_fault==8 ? 8 :
                        injected_fault==2 || injected_fault==3 ? 1 : 0;
        expected_drain_beats = injected_fault==2 || injected_fault==8 ? 9 : 8;
        write_reg(8'h30,256,4'hf,0,0,OKAY);
        write_reg(8'h34,0,4'hf,0,0,OKAY);
        write_reg(8'h38,1,4'hf,0,0,OKAY);
        await_transport(!hold_ar);
        if (injected_fault == 9) begin
            while (response_count < 3) tick();
            hold_r = 1;
        end
        if (injected_fault == 10)
            while (response_count < 8) tick();
        if (cancel_case) begin
            check_read(8'h64,still_pending ? 99 : 97);
            write_reg(8'h64,0,4'hf,0,0,SLVERR);
        end else begin
            status = 0;
            for (int attempt = 0; !status[1] && attempt < 44; attempt++) begin
                repeat(100) tick();
                read_reg(8'h28,0,OKAY,status);
            end
            if (!status[1] || !status[2] || status[11:8] != 5)
                $fatal(1,"Did not terminate with an autonomous fault: %h",status);
            check_read(8'h64,still_pending ? 103 : 101);
            check_read(8'h68,0);
            check_read(8'h6c,injected_fault == 4 ? 0 : 1);
            check_read(8'h70,32'(initial_beats));
            check_read(8'h74,1);
            check_read(8'h84,1);
            if (dut.core.output_projection.step_valid) $fatal(1,"Faulty row reached MAC");
        end
        write_reg(8'h1c,2,4'hf,0,0,OKAY);
        check_read(8'h60,0);
        check_read(8'h64,still_pending ? 2 : 8);
        check_read(8'h68,0);
        check_read(8'h74,0);
        if (still_pending) begin
            write_reg(8'h60,DDR_BASE,4'hf,0,0,SLVERR);
            hold_ar = 0;
            hold_r = 0;
            repeat(80) tick();
        end
        check_read(8'h64,8);
        if (command_count != 1 || response_count != expected_drain_beats)
            $fatal(1,"Fault recovery command / response count %d / %d",command_count,response_count);
        check_read(8'h6c,0);
        check_read(8'h70,0);

        word_count = 0;
        for (integer bank=0;bank<15;bank=bank+1) begin
            if (bank_length(bank)!=0) begin
                write_reg(8'h04,32'(bank),4'hf,1,0,OKAY);write_reg(8'h08,0,4'hf,2,0,OKAY);
                for (integer address=0;address<bank_length(bank);address=address+1) begin
                    write_reg(8'h0c,words[word_count],4'hf,0,0,OKAY);word_count=word_count+1;
                end
            end
        end
        run_bos(0);
        if (command_count != 1) $fatal(1,"Recovered BRAM arm started an AXI command");
        $display("DDR fault %0d drained commands=%0d beats=%0d",injected_fault,command_count,response_count);
        write_reg(8'h1c,1,4'hf,0,0,OKAY);
        @(negedge aclk);
        read_within_projection = 0;
        inject_bad_resp = 0;
        write_reg(8'h60,DDR_BASE,4'hf,0,0,OKAY);
        write_reg(8'h64,3,4'hf,0,0,OKAY);
        run_bos(1);
        check_read(8'h6c,32);
        check_read(8'h70,256);
        check_read(8'h68,2048);
        if (command_count != 33) $fatal(1,"Recovered row mode did not fetch a fresh first row");
        $display("PASS DDR fault or cancel %0d, exact BRAM and fresh row DDR BOS",injected_fault);
        $finish;
    endtask
